#!/usr/bin/env python3
"""
港股股票列表同步脚本（协作单 30.0 V2 / M2）

从 Yahoo 数据源拉取港股标的列表（^HSI/^HSCE 成分并集），写入 stock_basic 表。

写入规范（market='hk'）：
- code：规范化后带 .HK 后缀（如 9988.HK / 1.HK），与 stock_basic 主键 code 对齐
- name：暂存 Yahoo 原始符号；exchange='HKEX'，currency='HKD'，timezone='Asia/Hong_Kong'
- 采用独立 psycopg2 写库路径（execute_values + ON CONFLICT (code) DO UPDATE），
  不影响 A 股主链路使用的 save_stock_basic（其键与列均为 A 股口径）。

用法：
    ./venv/bin/python backend/collector/etl/sync_hk_stock_list.py            # 同步入库
    ./venv/bin/python backend/collector/etl/sync_hk_stock_list.py --dry-run  # 仅查看不写入
"""
import os
import sys
import argparse
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# 保证 `import collector.* / utils.logger` 可解析（backend 目录入 sys.path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('hk_stock_list_sync')

# 项目根目录（.env 所在处）
BASE_DIR = Path(__file__).resolve().parents[3]

MARKET = 'hk'


# ==================== 数据库连接（独立 psycopg2 路径） ====================
def _load_dotenv() -> None:
    """读取项目根 .env（未设置环境变量时兜底），不覆盖已存在的环境变量。"""
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _make_dsn() -> str:
    """构造 PostgreSQL 连接串（优先 DATABASE_URL，否则拼接 PG_*）。"""
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
    """建立连接（并发连接失败时抛异常，由调用方捕获）。"""
    _load_dotenv()
    return psycopg2.connect(_make_dsn())


# ==================== 股票列表同步 ====================
def _fetch_stock_list() -> pd.DataFrame:
    """从 AkShare（新浪）拉取港股列表并整理为 stock_basic 入库列。

    K 2026-09-04 起弃用 Yahoo：港股列表改由 AkShare 新浪全市场接口获取。

    Returns:
        DataFrame：code, name, exchange, market, currency, timezone
    """
    from collector.datasource.akshare import AkShareDataSource

    src = AkShareDataSource(market=MARKET)
    if not src.connect():
        raise RuntimeError('AkShare 数据源连接失败，无法拉取港股列表')
    df = src.get_stock_list()

    if df.empty:
        logger.warning('⚠️ AkShare 返回港股列表为空（可能接口限流）')
        return pd.DataFrame(columns=['code', 'name', 'exchange', 'market', 'currency', 'timezone'])

    df = df.copy()
    df['exchange'] = 'HKEX'
    df['market'] = MARKET
    df['currency'] = 'HKD'
    df['timezone'] = 'Asia/Hong_Kong'
    # code 已由适配器规范化；此处兜底再规范化一次（幂等）
    df['code'] = df['code'].astype(str)
    logger.info(f"✅ 获取港股列表 {len(df)} 只（AkShare 新浪全市场）")
    return df[['code', 'name', 'exchange', 'market', 'currency', 'timezone']]


def sync_stock_list(dry_run: bool = False) -> int:
    """同步港股列表到 stock_basic（execute_values + ON CONFLICT (code) DO UPDATE）。

    Args:
        dry_run: 为 True 时仅打印待写入数据，不落库

    Returns:
        写入/预计写入的港股数量
    """
    df = _fetch_stock_list()
    if df.empty:
        return 0

    if dry_run:
        logger.info('[DRY-RUN] 以下港股将写入 stock_basic（不落库）:')
        logger.info(df.head(20).to_string(index=False))
        logger.info(f"[DRY-RUN] 共 {len(df)} 条待写入")
        return len(df)

    values = list(df.itertuples(index=False, name=None))
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
        logger.info(f"✅ 港股列表同步完成: {len(values)} 条写入/覆盖 stock_basic")
        return len(values)
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ 港股列表同步失败: {e}")
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='港股股票列表同步脚本')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（只查看不写入）')
    args = parser.parse_args()

    try:
        count = sync_stock_list(dry_run=args.dry_run)
        if count == 0 and not args.dry_run:
            logger.warning('⚠️ 未同步到任何港股，请检查 AkShare 接口与网络')
    except Exception as e:
        logger.error(f'程序异常: {e}')
        raise


if __name__ == '__main__':
    main()