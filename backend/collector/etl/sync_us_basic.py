#!/usr/bin/env python3
"""
美股基本面同步脚本（AkShare 版本，恢复美股基本面监控）

背景：原实现依赖 Yahoo/yfinance 抓取美股基本面（total_mv/pe/pb 等），
K 2026-09-04 因 Yahoo 限流严重、不稳定已弃用并删除 YahooDataSource 与 sync_us_basic。
本项目港股/美股日线已切换至 AkShare，本脚本沿用同一数据源恢复美股基本面同步：
用 `ak.stock_us_spot()`（新浪美股实时行情）一次性快照，映射：
  mktcap → total_mv（总市值）、pe → pe（市盈率）。
说明：新浪该接口不含市净率 pb / pe_ttm / year_high / year_low，故这些字段留空
（K 2026-09-08 确认：先满足 市值+PE 即可）。

字段写入 stock_daily_basic（market='us'），ON CONFLICT (market, code, trade_date) 更新。
close 取 stock_quotes 对应交易日期的后复权收盘价（adj_close）。

用法：
    ./venv/bin/python backend/collector/etl/sync_us_basic.py               # 默认=美股最新交易日
    ./venv/bin/python backend/collector/etl/sync_us_basic.py --date 2026-09-04
    ./venv/bin/python backend/collector/etl/sync_us_basic.py --dry-run --limit 5
"""
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

# 保证 `import utils.logger / collector.datasource.yahoo` 可解析（脚本独立运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('us_basic_sync')

MARKET = 'us'
CYCLE = '1d'
DEFAULT_EXCHANGE = 'NAS'       # 美股缺失交易所缩写时兜底

# 如需控制新浪分页/批量可调；ak.stock_us_spot() 内部逐只抓取全市场，约 5~10 分钟。
RATE_LIMIT_SLEEP = 0.5         # 备用节流，接口非逐只调用时无需额外等待


def _ak() -> 'ak':
    """延迟 import akshare（仅在真正抓取时导入，加快 --dry-run / 参数错误路径）。"""
    import akshare as ak
    return ak


# ==================== 数据库连接（独立 psycopg2 路径） ====================
def _load_dotenv() -> None:
    """读取项目根 .env（未设置环境变量时兜底），不覆盖已存在的环境变量。"""
    env_path = Path(__file__).resolve().parents[3] / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        if key and key not in os.environ:
            os.environ[key.strip()] = value.strip()


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


def _connect():
    """建立连接（连接失败时抛异常）。"""
    _load_dotenv()
    import psycopg2
    return psycopg2.connect(_make_dsn())


# ==================== DB 辅助 ====================
def _list_us_codes(conn) -> List[str]:
    """获取 market='us' 的代码列表（从 stock_basic）。"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM stock_basic WHERE market = %s ORDER BY code", (MARKET,))
            return [r[0] for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 - 查询失败降级为空列表，由其调用方决定
        logger.warning(f"⚠️ 查询美股代码列表失败: {e}")
        return []


def _latest_trade_date(conn) -> Optional[str]:
    """查询 stock_quotes 中 market='us' 的最新交易日。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(trade_date)::text FROM stock_quotes WHERE market = %s AND cycle = %s",
                (MARKET, CYCLE),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ 查询美股最新交易日失败: {e}")
        return None


def _closes_map(conn, trade_date: str, codes: List[str]) -> Dict[str, float]:
    """批量取指定交易日 stock_quotes 的后复权收盘价 {code: adj_close}。"""
    if conn is None or not codes:
        return {}
    import psycopg2
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


def _existing_columns(conn, table: str) -> Set[str]:
    """查询表的现存列名集合（动态剔除不存在的写列）。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            return {r[0] for r in cur.fetchall()}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ 查询 {table} 列名失败: {e}")
        return set()


def write_daily_basic(conn, df: pd.DataFrame, trade_date: str) -> int:
    """写入 stock_daily_basic（ON CONFLICT (market, code, trade_date)）。

    Args:
        conn: 数据库连接
        df: 列含 code/trade_date/market + 可写基本面字段（total_mv/pe/close...）
        trade_date: 写入的交易日期（YYYY-MM-DD）

    Returns:
        写入条数
    """
    if df is None or df.empty:
        return 0
    from psycopg2.extras import execute_values

    existing = _existing_columns(conn, 'stock_daily_basic')
    writeable = [c for c in df.columns if c in existing]
    dropped = [c for c in df.columns if c not in existing and c not in (
        'code', 'trade_date', 'market')]
    if dropped:
        logger.info(f"  ℹ️ 以下字段在 stock_daily_basic 无对应列，已跳过: {sorted(set(dropped))}")

    order = ['code', 'trade_date', 'market']
    cols = order + [c for c in writeable if c not in order]

    def _to_py(v):
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
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        logger.error(f"❌ 写入 stock_daily_basic 失败: {e}")
        raise


# ==================== 基本面抓取与同步 ====================
def _fetch_spot_df() -> pd.DataFrame:
    """调用 ak.stock_us_spot() 抓取新浪美股全市场快照。

    Returns:
        原始 DataFrame（列含 name/cname/symbol/price/.../mktcap/pe）
    """
    ak = _ak()
    df = ak.stock_us_spot()
    if df is None or df.empty:
        raise RuntimeError('ak.stock_us_spot() 返回空数据，无法抓取美股基本面')
    logger.info(f"📡 新浪美股快照共 {len(df)} 行")
    return df


def _unit_of_mktcap(df: pd.DataFrame) -> str:
    """推算新浪美股 mktcap 单位（'yuan' 已用元 / 'yi' 为亿元，需 ×1e8）。

    启发式：取排名前若干市值样本，若绝对量级普遍 < 5e6 视为「亿元」（再 ×1e8）；
    否则按「元」。仅作防御性兜底，避免量纲错乱。
    """
    col = 'mktcap'
    if col not in df.columns:
        return 'yuan'
    s = pd.to_numeric(df[col], errors='coerce').dropna()
    if s.empty:
        return 'yuan'
    top = s.nlargest(20).abs()
    if top.max() > 0 and top.max() <= 2_000_000:  # 亿元量级（如 4000 → 4000 亿元）
        return 'yi'
    return 'yuan'


def _build_rows(spot: pd.DataFrame, codes: List[str]) -> List[Dict[str, object]]:
    """从 AkShare 快照构建落库行（仅保留 stock_basic 中已入库的美股代码）。

    Args:
        spot: ak.stock_us_spot() 返回的快照
        codes: 需要同步的美股代码列表（stock_basic market='us'）

    Returns:
        rows：含 code/market/total_mv/pe/currency/exchange
    """
    if spot is None or spot.empty or 'symbol' not in spot.columns:
        logger.warning('⚠️ 快照缺少 symbol 列，无法映射')
        return []

    unit = _unit_of_mktcap(spot)
    factor = 1e8 if unit == 'yi' else 1.0
    if factor != 1.0:
        logger.info(f"  ℹ️ 新浪 mktcap 判定为亿元单位，×1e8 转为元")

    df = spot[['symbol', 'mktcap', 'pe', 'price']].copy()
    df.columns = ['code', 'total_mv', 'pe', 'close']
    df['code'] = df['code'].astype(str).str.strip().str.upper()
    df = df[df['code'].isin(set(codes))]
    df = df.drop_duplicates(subset=['code']).copy()
    df['total_mv'] = pd.to_numeric(df['total_mv'], errors='coerce') * factor
    df['pe'] = pd.to_numeric(df['pe'], errors='coerce')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['market'] = MARKET
    df['currency'] = 'USD'
    df['exchange'] = DEFAULT_EXCHANGE
    return df.to_dict('records')


def sync_basic(conn, trade_date: str, limit: Optional[int] = None,
               dry_run: bool = False) -> int:
    """同步美股基本面到 stock_daily_basic。

    Args:
        conn: 数据库连接（dry_run 时可为 None）
        trade_date: 目标交易日（YYYY-MM-DD）
        limit: 最多同步条数
        dry_run: 试运行模式（抓取并打印、不落库）

    Returns:
        写入/预计写入条数
    """
    codes = _list_us_codes(conn) if conn else []
    if not codes:
        logger.warning('⚠️ stock_basic 无美股代码，跳过基本面同步')
        return 0

    spot = _fetch_spot_df()
    rows = _build_rows(spot, codes)
    if not rows:
        logger.warning('⚠️ 快照与美股代码无交集（可能全部退市/接口异常）')
        return 0
    if limit:
        rows = rows[:limit]

    df = pd.DataFrame(rows)
    # close 用 stock_quotes 该交易日后复权收盘价覆盖（保证与行情日期对齐）
    if conn is not None:
        closes = _closes_map(conn, trade_date, df['code'].tolist())
        if closes:
            df['close'] = df['code'].map(closes).fillna(df['close'])
    df['trade_date'] = pd.Timestamp(trade_date)
    df = df.where(pd.notnull(df), None)

    logger.info(f"📊 同步 {len(df)} 只美股基本面，目标交易日 {trade_date}")

    if dry_run:
        logger.info('[DRY-RUN] 以下将写入 stock_daily_basic（不落库）:')
        show_cols = [c for c in ['code', 'trade_date', 'market', 'total_mv', 'pe',
                                 'currency', 'exchange', 'close'] if c in df.columns]
        logger.info(df[show_cols].head(10).to_string(index=False))
        logger.info(f'[DRY-RUN] 共 {len(df)} 条待写入')
        return len(df)

    if conn is None:
        raise RuntimeError('非 dry-run 模式必须提供数据库连接')
    return write_daily_basic(conn, df, trade_date)


def main() -> None:
    parser = argparse.ArgumentParser(description='美股基本面同步脚本（AkShare 快照，市值+PE）')
    parser.add_argument('--date', type=str, default=None, help='目标交易日（YYYY-MM-DD），默认=最新交易日')
    parser.add_argument('--limit', type=int, default=None, help='最多同步条数（调试用）')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（抓取并打印、不落库）')
    args = parser.parse_args()

    # dry-run 也连库：用于读取美股代码列表做真实映射验证；写库仅在非 dry-run 分支执行，安全。
    conn = _connect()
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
    except Exception as e:  # noqa: BLE001
        logger.error(f'程序异常: {e}')
        raise
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    main()