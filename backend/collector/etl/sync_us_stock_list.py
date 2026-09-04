#!/usr/bin/env python3
"""
美股股票列表同步脚本（协作单 30.0 V3 / M3）

从内置核心池清单（backend/config/us_core_universe.json，K 批示 ~600 只精简版 ~211 只）
经 AkShare 读取后写入 stock_basic 表。

K 2026-09-04 起弃用 Yahoo：不再逐个 Yahoo Ticker.info 校验有效性（风控/限流频繁），
直接经 AkShareDataSource.get_stock_list() 读取核心池清单生成入库行。

写入规范（market='us'）：
- code：Yahoo 格式大写（如 AAPL / MSFT / BRK-B）
- name：核心池清单代码（无独立名称映射时暂用代码本身）
- exchange：'NMS'；currency='USD'；timezone='America/New_York'
- 独立 psycopg2 写库（execute_values + ON CONFLICT (code) DO UPDATE）

用法：
    ./venv/bin/python backend/collector/etl/sync_us_stock_list.py            # 同步入库
    ./venv/bin/python backend/collector/etl/sync_us_stock_list.py --dry-run  # 仅查看
"""
import os
import sys
import argparse
import json
from pathlib import Path
from typing import List

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('us_stock_list_sync')

BASE_DIR = Path(__file__).resolve().parents[3]

MARKET = 'us'
UNIVERSE_PATH = BASE_DIR / 'backend/config/us_core_universe.json'


# ==================== 数据库连接 ====================
def _load_dotenv() -> None:
    """读取项目根 .env（未设置环境变量时兜底），不覆盖已存在环境变量。"""
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _make_dsn() -> str:
    """构造 PostgreSQL 连接串。"""
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    required = ['PG_HOST', 'PG_PORT', 'PG_DATABASE', 'PG_USER', 'PG_PASSWORD']
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"缺少数据库连接配置: {', '.join(missing)}")
    return (
        f"host={os.environ['PG_HOST']} port={os.environ['PG_PORT']} "
        f"dbname={os.environ['PG_DATABASE']} user={os.environ['PG_USER']} "
        f"password={os.environ['PG_PASSWORD']}"
    )


def _connect() -> psycopg2.extensions.connection:
    """建立连接。"""
    _load_dotenv()
    return psycopg2.connect(_make_dsn())


# ==================== 列表来源与整理 ====================
def _load_core_pool() -> List[str]:
    """读取美股核心池清单代码（us_core_universe.json）。"""
    try:
        data = json.loads(UNIVERSE_PATH.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"❌ 读取核心池清单失败: {e}")
        return []
    symbols = data.get('symbols', []) if isinstance(data, dict) else []
    return [s.strip() for s in symbols if str(s).strip()]


def _fetch_stock_list() -> pd.DataFrame:
    """用 AkShare 读取美股核心池清单并整理为 stock_basic 入库列。

    K 2026-09-04 起弃用 Yahoo：不再逐个 Yahoo Ticker.info 校验（风控/限流频繁），
    直接经 AkShareDataSource.get_stock_list() 读取核心池清单生成入库行。
    """
    from collector.datasource.akshare import AkShareDataSource

    src = AkShareDataSource(market=MARKET)
    if not src.connect():
        raise RuntimeError('AkShare 数据源连接失败，无法拉取美股列表')
    df = src.get_stock_list()

    if df.empty:
        logger.warning('⚠️ AkShare 返回美股列表为空')
        return pd.DataFrame(columns=['code', 'name', 'exchange', 'market', 'currency', 'timezone'])

    df = df.copy()
    df['exchange'] = 'NMS'
    df['market'] = MARKET
    df['currency'] = 'USD'
    df['timezone'] = 'America/New_York'
    # code 已由适配器规范化；此处兜底再规范化一次（幂等）
    df['code'] = df['code'].astype(str)
    logger.info(f"✅ 获取美股列表 {len(df)} 只（AkShare 核心池清单）")
    return df[['code', 'name', 'exchange', 'market', 'currency', 'timezone']]


# ==================== 列表同步 ====================
def sync_stock_list(dry_run: bool = False) -> int:
    """同步美股核心池到 stock_basic（execute_values + ON CONFLICT (code) DO UPDATE）。"""
    codes = _load_core_pool()
    if not codes:
        logger.error('❌ 核心池代码为空，无法同步')
        return 0
    logger.info(f"🚀 核心池共 {len(codes)} 只，开始经 AkShare 读取...")
    df = _fetch_stock_list()
    if df.empty:
        logger.warning('⚠️ 读取后无有效美股，未同步')
        return 0

    if dry_run:
        logger.info('[DRY-RUN] 以下美股将写入 stock_basic（不落库）:')
        logger.info(df.head(20).to_string(index=False))
        logger.info(f"[DRY-RUN] 共 {len(df)} 条待写入")
        return len(df)

    values = list(df[['code', 'name', 'exchange', 'market', 'currency', 'timezone']].itertuples(index=False, name=None))
    conn = _connect()
    try:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO stock_basic (code, name, exchange, market, currency, timezone)
                VALUES %s
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    exchange = EXCLUDED.exchange,
                    market = EXCLUDED.market,
                    currency = EXCLUDED.currency,
                    timezone = EXCLUDED.timezone,
                    updated_at = CURRENT_TIMESTAMP
            """, values, page_size=2000)
        conn.commit()
        logger.info(f"✅ 美股列表同步完成: {len(values)} 条写入/覆盖 stock_basic")
        return len(values)
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 美股列表同步失败: {e}")
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='美股股票列表同步脚本')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（只校验+查看不写入）')
    args = parser.parse_args()

    try:
        count = sync_stock_list(dry_run=args.dry_run)
        if count == 0 and not args.dry_run:
            logger.warning('⚠️ 未同步到任何美股，请检查核心池清单与 AkShare 接口')
    except Exception as e:
        logger.error(f'程序异常: {e}')
        raise


if __name__ == '__main__':
    main()