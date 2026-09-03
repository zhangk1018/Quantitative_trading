#!/usr/bin/env python3
"""
美股基本面同步脚本（协作单 30.0 V3 / M3）

对美股清单内标的低频调用 Yahoo 基本面接口（Ticker.info 风控较严，勿每日全市场遍历），
写入 stock_daily_basic（market='us'）。

字段映射见 YahooDataSource.get_fundamentals / MarketConfig.fundamental_fields：
  marketCap→total_mv, trailingPE→pe, priceToBook→pb, fiftyTwoWeekHigh→year_high,
  fiftyTwoWeekLow→year_low, currency, exchange, timezoneName→timezone。
stock_daily_basic（V010 已含 currency/exchange/timezone/year_high/year_low 列）：
pe/pe_ttm/pb/total_mv/close 等基础字段直接映射；exchange 缺省置为 'NAS'。
close 取 stock_quotes 该交易日的后复权收盘价（adj_close）。

ON CONFLICT 键与真实约束核对一致：uk_daily_basic_market_code_date (market, code, trade_date)。

用法：
    ./venv/bin/python backend/collector/etl/sync_us_basic.py                     # 最新交易日，全部
    ./venv/bin/python backend/collector/etl/sync_us_basic.py --date 2026-09-02 --limit 10
    ./venv/bin/python backend/collector/etl/sync_us_basic.py --dry-run --limit 5
"""
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# 保证 `import collector.* / utils.logger` 可解析
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import setup_logger  # noqa: E402
from collector.datasource.yahoo import YahooDataSource, normalize_code  # noqa: E402

logger = setup_logger('us_basic_sync')

BASE_DIR = Path(__file__).resolve().parents[3]

MARKET = 'us'
CYCLE = '1d'
DEFAULT_EXCHANGE = 'NAS'       # 美股缺失 exchange 时兜底交易所缩写


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
    """建立连接（连接失败时抛异常，由调用方捕获）。"""
    _load_dotenv()
    return psycopg2.connect(_make_dsn())


# ==================== DB 辅助 ====================
def _list_us_codes(conn: Optional[psycopg2.extensions.connection],
                   src: Optional[YahooDataSource] = None) -> List[str]:
    """获取 market='us' 的代码列表。

    优先从 stock_basic 读已入库美股代码；若为空降级调用 YahooDataSource.get_market_list('us')。

    Args:
        conn: 数据库连接（可为 None）
        src: Yahoo 数据源（降级拉取列表用）

    Returns:
        规范化美股代码列表
    """
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT code FROM stock_basic WHERE market = %s ORDER BY code", (MARKET,))
                codes = [r[0] for r in cur.fetchall()]
            if codes:
                return codes
            logger.info("  📋 stock_basic 尚无美股代码，改从 Yahoo 核心池清单兜底")
        except psycopg2.DatabaseError as e:
            logger.warning(f"⚠️ 查询美股代码列表失败（改用 Yahoo 清单兜底）: {e}")
    if src is not None:
        df = src.get_market_list(MARKET)
        if df is not None and not df.empty:
            return [normalize_code(str(c), MARKET) for c in df['code'].tolist()]
        logger.warning("⚠️ Yahoo 核心池清单不可用，返回空列表")
    return []


def _latest_trade_date(conn: psycopg2.extensions.connection) -> Optional[str]:
    """查询 stock_quotes 中 market='us' 的最新交易日。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(trade_date)::text FROM stock_quotes WHERE market = %s AND cycle = %s",
                (MARKET, CYCLE),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    except psycopg2.DatabaseError as e:
        logger.warning(f"⚠️ 查询美股最新交易日失败: {e}")
        return None


def _closes_map(conn: psycopg2.extensions.connection, trade_date: str, codes: List[str]) -> Dict[str, float]:
    """批量取指定交易日 stock_quotes 的后复权收盘价 {code: adj_close}。"""
    if conn is None or not codes:
        return {}
    result: Dict[str, float] = {}
    batch_size = 2000
    try:
        with conn.cursor() as cur:
            for i in range(0, len(codes), batch_size):
                batch = codes[i:i + batch_size]
                cur.execute(
                    "SELECT code, adj_close FROM stock_quotes "
                    "WHERE market = %s AND cycle = %s AND trade_date = %s AND code = ANY(%s)"
                    " AND adj_close IS NOT NULL",
                    (MARKET, CYCLE, trade_date, batch),
                )
                for code, close in cur.fetchall():
                    result[code] = float(close)
    except psycopg2.DatabaseError as e:
        logger.warning(f"⚠️ 批量查询收盘价失败（忽略 close，non-fatal）: {e}")
    return result


def _existing_columns(conn: psycopg2.extensions.connection, table: str) -> Set[str]:
    """查询表的现存列名集合（用于动态剔除不存在的写列）。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            return {r[0] for r in cur.fetchall()}
    except psycopg2.DatabaseError as e:
        logger.warning(f"⚠️ 查询 {table} 列名失败: {e}")
        return set()


def write_daily_basic(conn: psycopg2.extensions.connection, df: pd.DataFrame, trade_date: str) -> int:
    """写入 stock_daily_basic（ON CONFLICT (market, code, trade_date)）。

    Args:
        conn: 数据库连接
        df: 列含 code/trade_date/market + 可写基本面字段（total_mv/pe/pb/close...）
        trade_date: 写入的交易日期（YYYY-MM-DD）

    Returns:
        写入条数
    """
    if df is None or df.empty:
        return 0
    # 动态剔除表内不存在的列（防御未来缺列的迁移状态）
    existing = _existing_columns(conn, 'stock_daily_basic')
    writeable = [c for c in df.columns if c in existing]
    dropped = [c for c in df.columns if c not in existing and c not in (
        'code', 'trade_date', 'market')]
    if dropped:
        logger.info(f"  ℹ️ 以下字段在 stock_daily_basic 无对应列，已跳过: {sorted(set(dropped))}")

    # 保证写入固定顺序：code, trade_date, market, 其余字段
    order = ['code', 'trade_date', 'market']
    cols = order + [c for c in writeable if c not in order]

    def _to_py(v):
        # float NaN 统一成 None（落库为 NULL，避免 numeric 存 Decimal('NaN')）
        if isinstance(v, float) and pd.isna(v):
            return None
        if isinstance(v, (pd.Timestamp,)):
            return v.date()
        return v

    values = []
    for r in df.to_dict('records'):
        values.append(tuple(_to_py(r.get(c)) for c in cols))

    set_clause = ', '.join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ('code', 'trade_date', 'market'))
    if not set_clause:
        set_clause = 'market = EXCLUDED.market'
    try:
        with conn.cursor() as cur:
            execute_values(cur, f"""
                INSERT INTO stock_daily_basic ({', '.join(cols)})
                VALUES %s
                ON CONFLICT (market, code, trade_date) DO UPDATE SET {set_clause}
            """, values, page_size=2000)
        conn.commit()
        logger.info(f"✅ 写入 stock_daily_basic {len(values)} 条（{trade_date}）")
        return len(values)
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"❌ 写入 stock_daily_basic 失败: {e}")
        raise


# ==================== 基本面抓取与同步 ====================
def _fetch_basic_rows(src: YahooDataSource, codes: List[str]) -> List[Dict[str, object]]:
    """对清单内股票逐个抓取基本面，返回 rows（含 code/market + 可用字段）。

    补充：exchange 缺失时兜底置 DEFAULT_EXCHANGE（'NAS'），对齐美股落库口径。
    """
    rows: List[Dict[str, object]] = []
    for i, code in enumerate(codes, 1):
        info = src.get_fundamentals(code, MARKET)
        if not info:
            logger.info(f"  {code}: 基本面为空（可能退市/限流），跳过")
            continue
        row: Dict[str, object] = {'code': code, 'market': MARKET}
        row.update(info)  # total_mv/pe/pb/year_high/year_low/currency/exchange/timezone
        if not row.get('exchange'):
            row['exchange'] = DEFAULT_EXCHANGE
        rows.append(row)
        if i % 20 == 0:
            logger.info(f"  进度 {i}/{len(codes)}")
    return rows


def sync_basic(conn: Optional[psycopg2.extensions.connection], trade_date: str,
               limit: Optional[int] = None, dry_run: bool = False) -> int:
    """同步美股基本面到 stock_daily_basic。

    Args:
        conn: 数据库连接（dry_run 时可为 None）
        trade_date: 目标交易日（YYYY-MM-DD）
        limit: 最多同步条数
        dry_run: 试运行模式（抓取并打印、不落库）

    Returns:
        写入/预计写入条数
    """
    src = YahooDataSource(market=MARKET)
    if not src.connect():
        raise RuntimeError('Yahoo 数据源连接失败，无法抓取美股基本面')

    codes = _list_us_codes(conn if not dry_run else None, src) if not dry_run else ['AAPL', 'MSFT']
    if limit:
        codes = codes[:limit]

    logger.info(f"📊 同步 {len(codes)} 只美股基本面，目标交易日 {trade_date}")
    rows = _fetch_basic_rows(src, codes)
    if not rows:
        logger.warning('⚠️ 未抓到任何基本面数据（可能全被限流）')
        return 0

    df = pd.DataFrame(rows)
    df['code'] = df['code'].apply(lambda x: normalize_code(str(x), MARKET))
    df['trade_date'] = pd.Timestamp(trade_date)
    df = df.dropna(subset=['code'])

    # close 从 stock_quotes 补（后复权收盘价）
    if conn is not None and 'code' in df.columns:
        closes = _closes_map(conn, trade_date, df['code'].tolist())
        if closes:
            df['close'] = df['code'].map(closes)
        else:
            df['close'] = None

    # NaN -> None：psycopg2 无法适配 float NaN
    df = df.where(pd.notnull(df), None)

    if dry_run:
        logger.info('[DRY-RUN] 以下将写入 stock_daily_basic（不落库）:')
        show_cols = [c for c in ['code', 'trade_date', 'market', 'total_mv', 'pe', 'pb',
                                 'currency', 'exchange', 'year_high', 'year_low', 'close'] if c in df.columns]
        logger.info(df[show_cols].head(20).to_string(index=False))
        logger.info(f'[DRY-RUN] 共 {len(df)} 条待写入')
        return len(df)

    if conn is None:
        raise RuntimeError('非 dry-run 模式必须提供数据库连接')
    return write_daily_basic(conn, df, trade_date)


def main() -> None:
    parser = argparse.ArgumentParser(description='美股基本面同步脚本')
    parser.add_argument('--date', type=str, default=None, help='目标交易日（YYYY-MM-DD），默认=最新交易日')
    parser.add_argument('--limit', type=int, default=None, help='最多同步条数（调试用）')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（抓取并打印、不落库）')
    args = parser.parse_args()

    conn = _connect() if not args.dry_run else None
    try:
        trade_date = args.date
        if not trade_date:
            if conn:
                trade_date = _latest_trade_date(conn)
            if not trade_date:
                from datetime import date
                trade_date = date.today().isoformat()
                logger.info(f"📅 未指定 --date 且无美股行情，用今日 {trade_date} 顶替（仅影响 close 补全）")
        count = sync_basic(conn, trade_date, limit=args.limit, dry_run=args.dry_run)
        logger.info(f"完成: {count} 条")
    except Exception as e:
        logger.error(f'程序异常: {e}')
        raise
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    main()