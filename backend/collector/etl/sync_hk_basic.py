#!/usr/bin/env python3
"""
港股基本面同步脚本（AkShare 百度估值版，低频）

背景：原实现依赖 Yahoo/yfinance 抓取港股基本面（total_mv/pe/pb），K 2026-09-04 已弃用 Yahoo。
港股没有美股那样的一次性全市场估值接口：
  - 新浪 stock_hk_spot() 仅返回行情 OHLCV，不含市值/PE；
  - 东财 stock_hk_spot_em() 等被网络拦截（与美股一致）；
  - 百度 gushitong 估值接口 `ak.stock_hk_valuation_baidu()` 可通但为「逐只 + 逐指标」。
故本脚本采用百度逐只拉取「总市值 + 市盈率(TTM)」写 stock_daily_basic（market='hk'），
单只约 0.5s/次、全市场 2000+ 只需较长耗时，适合一次性补库或低频调度，不宜每日串行。

字段映射：
  indicator='总市值'   → total_mv（百度返回单位为「亿元 HKD」，×1e8 转元）
  indicator='市盈率(TTM)' → pe
  currency='HKD'，exchange 缺省兜底 'SEHK'。
  close 取 stock_quotes 该交易日后复权收盘价（adj_close）。

用法：
    ./venv/bin/python backend/collector/etl/sync_hk_basic.py                 # 默认=港股利好最新交易日
    ./venv/bin/python backend/collector/etl/sync_hk_basic.py --date 2026-09-07
    ./venv/bin/python backend/collector/etl/sync_hk_basic.py --dry-run --limit 5
"""
import os
import sys
import argparse
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

# 保证 `import utils.logger` 可解析（脚本独立运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('hk_basic_sync')

MARKET = 'hk'
CYCLE = '1d'
CURRENCY = 'HKD'
DEFAULT_EXCHANGE = 'SEHK'

# 百度估值：单位「亿港币」→ 元港币 系数
_MV_YI_FACTOR = 1e8
# 逐只请求间最小休眠（秒），避免触发百度限流
_REQUEST_SLEEP = 0.20


def _ak():
    """延迟 import akshare（仅在真正抓取时导入）。"""
    import akshare as ak
    return ak


def _to_baidu_symbol(code: str) -> str:
    """港股代码规范化为百度 symbol（5 位数字串，如 '00700.HK' → '00700'、'1.HK' → '00001'）。

    百度股市通港股代码统一为 5 位前导零（'00001'/'00700'），不能截断成 4 位。
    """
    s = str(code).strip().upper()
    if s.endswith('.HK'):
        s = s[:-3]
    s = s.split('.')[0]
    try:
        digits = str(int(s))          # 去前导零再补零
    except ValueError:
        digits = s
    return digits.zfill(5)


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
def _list_hk_codes(conn) -> List[str]:
    """获取 market='hk' 的代码列表（从 stock_basic，保留 '.HK' 格式）。"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM stock_basic WHERE market = %s ORDER BY code", (MARKET,))
            return [r[0] for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ 查询港股代码列表失败: {e}")
        return []


def _latest_trade_date(conn) -> Optional[str]:
    """查询 stock_quotes 中 market='hk' 的最新交易日。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(trade_date)::text FROM stock_quotes WHERE market = %s AND cycle = %s",
                (MARKET, CYCLE),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ 查询港股最新交易日失败: {e}")
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
    """写入 stock_daily_basic（ON CONFLICT (market, code, trade_date)）。"""
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
def _fetch_value(code: str, indicator: str, trade_date: str) -> Optional[float]:
    """抓取单只股票某估值指标在 target_date 对应的值。

    百度按「近一年」返回日频 [date, value]；取等于 target_date 的行；若当日缺该值
    （如停牌/接口滞后）则回退到日期 ≤ target_date 的最近一行。

    Args:
        code: 港股 4 位代码（如 '00700'）
        indicator: 估值指标（'总市值' / '市盈率(TTM)'）
        trade_date: 目标交易日（YYYY-MM-DD）

    Returns:
        值（None 表示接口无数据）
    """
    ak = _ak()
    try:
        df = ak.stock_hk_valuation_baidu(symbol=code, indicator=indicator, period='近一年')
    except Exception as e:  # noqa: BLE001
        logger.warning(f"  {code} {indicator} 拉取失败: {type(e).__name__} {str(e)[:80]}")
        return None
    if df is None or df.empty or 'date' not in df.columns or 'value' not in df.columns:
        return None
    df = df.copy()
    df['date'] = df['date'].astype(str)
    exact = df.loc[df['date'] == trade_date, 'value']
    if not exact.empty:
        v = exact.iloc[0]
        return float(v) if pd.notna(v) else None
    # 取 ≤ target_date 最近一有效行
    pred = df.loc[df['date'] <= trade_date]
    if pred.empty:
        return None
    v = pred.sort_values('date').iloc[-1, pred.columns.get_loc('value')]
    return float(v) if pd.notna(v) else None


def sync_basic(conn, trade_date: str, limit: Optional[int] = None,
               dry_run: bool = False) -> int:
    """同步港股基本面（市值 + 市盈率 TTM）到 stock_daily_basic。

    Args:
        conn: 数据库连接
        trade_date: 目标交易日（YYYY-MM-DD）
        limit: 最多同步条数
        dry_run: 试运行模式（抓取并打印、不落库）

    Returns:
        写入/预计写入条数
    """
    codes = _list_hk_codes(conn) if conn else []
    if not codes:
        logger.warning('⚠️ stock_basic 无港股代码，跳过基本面同步')
        return 0
    if limit:
        codes = codes[:limit]

    logger.info(f"📊 同步 {len(codes)} 只港股基本面，目标交易日 {trade_date}")
    rows: List[Dict[str, object]] = []
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        sym = _to_baidu_symbol(code)
        mv = _fetch_value(sym, '总市值', trade_date)
        pe = _fetch_value(sym, '市盈率(TTM)', trade_date)
        if mv is None and pe is None:
            logger.info(f"  {code}: 百度估值无数据（可能退市/受限/停牌），跳过")
            continue
        row: Dict[str, object] = {'code': code, 'market': MARKET}
        if mv is not None:
            row['total_mv'] = mv * _MV_YI_FACTOR
        if pe is not None:
            row['pe'] = pe
        row['currency'] = CURRENCY
        row['exchange'] = DEFAULT_EXCHANGE
        rows.append(row)
        time.sleep(_REQUEST_SLEEP)
        if i % 200 == 0 or i == len(codes):
            elapsed = time.time() - t0
            logger.info(f"  进度 {i}/{len(codes)}（已抓取 {len(rows)} 只有值，耗时 {elapsed/60:.1f} min）")

    if not rows:
        logger.warning('⚠️ 未抓到任何港股基本面数据')
        return 0

    df = pd.DataFrame(rows)
    if conn is not None:
        closes = _closes_map(conn, trade_date, df['code'].tolist())
        if closes:
            df['close'] = df['code'].map(closes)
        else:
            df['close'] = None
    df['trade_date'] = pd.Timestamp(trade_date)
    df = df.where(pd.notnull(df), None)

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
    parser = argparse.ArgumentParser(description='港股基本面同步脚本（AkShare 百度估值，市值+市盈率TTM，低频）')
    parser.add_argument('--date', type=str, default=None, help='目标交易日（YYYY-MM-DD），默认=港股利好最新交易日')
    parser.add_argument('--limit', type=int, default=None, help='最多同步条数（调试用）')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（抓取并打印、不落库）')
    args = parser.parse_args()

    conn = _connect()
    try:
        trade_date = args.date
        if not trade_date:
            trade_date = _latest_trade_date(conn) or pd.Timestamp.today().strftime('%Y-%m-%d')
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