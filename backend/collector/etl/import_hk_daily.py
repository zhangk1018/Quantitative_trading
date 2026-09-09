#!/usr/bin/env python3
"""
港股日线行情下载脚本（协作单 30.0 V2 / M2）

从 AkShare（新浪财经）数据源拉取港股日线（不复权 + 后复权 hfq），
经复权工具拆分 raw_*/adj_*，标注意除权日，写入 stock_quotes 与 stock_adj_factor。

写入口径（对齐方案 v2 §1.2 / V009）：
- stock_quotes：cycle='1d'，market='hk'，成交价列 open/high/low/close 统一存【后复权价】
  （与指标/回测/前端统一用 adj_close 一致）；另存 raw_open..raw_close + adj_open..adj_close。
- 复权因子/除权日写 stock_adj_factor（market='hk'，factor_date 列），仅写入发生除权
  因子变化的因子日（避免以 ~1.0 的每日因子淹没该表）。
- 增量控制：读 etl_control 表 market='hk' 的 last_sync_date；--incremental 从 last_sync_date+1
  到今天，--init 全量（period='max'）；成功后回写 etl_control。

写入采用独立 psycopg2 路径（execute_values），不触碰 A 股主链路 save_quotes。
ON CONFLICT 键与真实约束核对一致：stock_quotes 主键 (code, cycle, trade_date)；
stock_adj_factor 用唯一键 uk_adj_factor_market_code_date (market, code, trade_date)。

用法：
    --test-one 9988.HK                                    # 拉单只验证
    --init [--limit 20] [--dry-run]                       # 全量
    --incremental [--limit 20] [--dry-run]                # 增量
"""
import os
import re
import sys
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
import requests
from psycopg2.extras import execute_values

# 保证 `import collector.* / collector.utils / utils.logger` 可解析
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import setup_logger  # noqa: E402
from collector.datasource.akshare import AkShareDataSource, normalize_code  # noqa: E402
from collector.utils.adj_adjust import split_raw_adj, detect_factor_dates  # noqa: E402
from collector.etl.market_download_common import (  # noqa: E402
    get_market_last_processed_code,
    set_market_last_processed_code,
    resume_codes,
    rate_limit_sleep,
)

logger = setup_logger('hk_daily_import')

# 项目根目录（.env 所在处）
BASE_DIR = Path(__file__).resolve().parents[3]

MARKET = 'hk'
CYCLE = '1d'
ADJUST_TYPE = 'adj'            # stock_quotes 成交价列存的复权口径（adj_close=后复权）
HOT = 'Asia/Hong_Kong'         # 港股收盘时区
MARKET_CLOSE_HHMM = '16:00:00'  # 港股收盘时间（生成 trade_datetime）

# 港交所官方「Dividends & Other Entitlements」全市场除权除息名单（单请求，日更）。
# 用于批量快照路径的**权威除权路由**：当日 Ex-Date（除净日）命中的股票无条件回退逐只
# 下载，消除启发式 2% 阈值对小幅除息（<2%）的漏检风险。
HKEX_EENT_URL = 'https://www3.hkexnews.hk/reports/doe/eent.htm'


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


# ==================== etl_control 增量控制 ====================
def get_last_sync_date(conn: psycopg2.extensions.connection) -> Optional[str]:
    """读取 etl_control 中 market='hk' 的 last_sync_date；无记录返回 None。"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_sync_date::text FROM etl_control WHERE market = %s",
                (MARKET,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None
    except psycopg2.DatabaseError as e:
        logger.warning(f"⚠️ 读取 etl_control 失败: {e}")
        return None


def set_last_sync_date(conn: psycopg2.extensions.connection, sync_date: str) -> None:
    """回写 etl_control 的 last_sync_date（ON CONFLICT (market) upsert）。"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO etl_control (market, last_sync_date, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (market) DO UPDATE SET
                    last_sync_date = EXCLUDED.last_sync_date,
                    updated_at = CURRENT_TIMESTAMP
            """, (MARKET, sync_date))
        conn.commit()
        logger.info(f"📝 已回写 etl_control last_sync_date = {sync_date}")
    except psycopg2.DatabaseError as e:
        conn.rollback()
        logger.warning(f"⚠️ 回写 etl_control 失败: {e}")


# ==================== 数据清洗与拆分 ====================
def _normalize_yahoo_cols(df: pd.DataFrame) -> pd.DataFrame:
    """统一 Yahoo 原生列为小写，并把索引 Date 提为 trade_date 列。"""
    out = df.copy()
    if out.index.name == 'Date' or isinstance(out.index, pd.DatetimeIndex):
        out = out.reset_index()
    ren = {}
    for c in out.columns:
        low = str(c).lower()
        if low == 'date':
            ren[c] = 'trade_date'
        elif low == 'adj close':
            ren[c] = 'adj_close'
        elif low == 'volume':
            ren[c] = 'volume'
        elif low in ('open', 'high', 'low', 'close'):
            ren[c] = low
        elif low == 'timezone':
            ren[c] = 'timezone'
    return out.rename(columns=ren)


def _guard_unadjusted_notches(splitted: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """拦截「孤立未复权错价」（协作单 32.0，P1 防复发）。

    新浪/雅虎后复权源在个别交易日可能返回 `Adj Close ≈ Close`（未复权），使该行
    `adj_factor≈1.0` 相对相邻平滑复权序列形成**孤立断崖**（相邻两日因子正常、仅当日
    突变），而真实除权除息会形成**持久因子块**（新因子延续多日）。本函数只剔除
    满足「前后相邻因子互相接近（非除权块）且当日因子显著偏离」的**孤立**行，避免
    误删真实除权边界。

    Args:
        splitted: `split_raw_adj` 输出（含 trade_date / adj_factor / volume 等）

    Returns:
        (过滤后的 DataFrame, 剔除行数)
    """
    if splitted.empty or 'adj_factor' not in splitted or 'trade_date' not in splitted:
        return splitted, 0

    df = splitted.reset_index(drop=True)
    factor = df['adj_factor'].astype(float)
    normal_ratio = 0.15        # 相邻因子相差 <15% 视为「平滑段」（互相接近）
    deviation = 0.6            # 当日因子 < 相邻因子×0.6 视为孤立偏离
    notch = pd.Series(False, index=df.index)
    for i in df.index:
        if i - 1 not in df.index or i + 1 not in df.index:
            continue  # 首尾行（含最新锚点，其 factor≈1.0 属正常）不判
        f_prev, f_cur, f_next = factor[i - 1], factor[i], factor[i + 1]
        # 相邻两日需互相接近（相差 < normal_ratio）才构成「前后平滑、仅当日突变」的孤立场景
        if f_prev <= 0 or f_next <= 0:
            continue
        denom = max(f_prev, f_next)
        if abs(f_prev - f_next) / denom > normal_ratio:
            continue  # 前后不等 → 真实除权边界，不判
        # 当日因子需显著低于相邻（< deviation×紧邻），否则不是向下的孤立错价
        if f_cur >= deviation * min(f_prev, f_next):
            continue
        notch[i] = True

    n = int(notch.sum())
    if n == 0:
        return splitted, 0
    logger.warning(
        f"⚠️ {df.loc[notch, 'code'].iloc[0] if 'code' in df else ''} 拦截 {n} 天"
        f"孤立未复权错价（Adj Close≈Close 断崖）："
        f"{pd.to_datetime(df.loc[notch, 'trade_date']).dt.date.astype(str).tolist()}，已剔除不入库"
    )
    return df.loc[~notch].reset_index(drop=True), n


def clean_and_split(df_raw: pd.DataFrame, code: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """把一个标的的 Yahoo 原生日线拆分为入库的行情/复权因子两部分。

    流程：列名规范化 → 剔除停牌 NaN 行 → split_raw_adj 拆 raw_*/adj_* →
    detect_factor_dates 标除权日 → 组装 stock_quotes 行（成交价列=后复权）与
    stock_adj_factor 行（仅除权因子日）。

    Args:
        df_raw: Yahoo 原生 DataFrame（Date/Open/High/Low/Close/Adj Close/Volume/Timezone）
        code: 规范化后的代码（如 9988.HK）

    Returns:
        (quotes_df, adj_factor_df)；任一为空返回 None
    """
    if df_raw is None or df_raw.empty:
        logger.info(f"  {code}: 返回空数据（可能停牌/无历史）")
        return None, None

    df = _normalize_yahoo_cols(df_raw)
    # 停牌统计：Yahoo 对停牌日返回 OHLC 全 NaN，剔除并计数
    suspended = int(df[['open', 'high', 'low', 'close', 'adj_close']].isna().any(axis=1).sum())
    cleaned = df.dropna(subset=['open', 'high', 'low', 'close', 'adj_close']).copy()
    if cleaned.empty:
        logger.info(f"  {code}: 全为停牌 NaN 行，无可入库数据")
        return None, None

    # 停牌超过阈值的标的记日志（cfg.suspended_log_threshold_days=30，见 MarketConfig）
    if suspended > 30:
        logger.info(f"  {code}: 本区间停牌约 {suspended} 天，已剔除 NaN 行")

    # 拆分原始价/后复权 + 标除权日
    splitted = split_raw_adj(
        cleaned.rename(columns={'adj_close': 'adj_close'}).copy(), keep=('open', 'high', 'low', 'close')
    )
    # 仙股 hfq 防护：新浪 hfq 对部分仙股返回负后复权价（adj_* 为负而 raw_* 为正）。
    # 负价会导致前端校验失败（StockResponse 价格字段 >= 0）并使技术指标失真，
    # 此处将负后复权价回退为对应原始价，并把该日因子置 1.0（无复权调整）。
    # 置于 detect_factor_dates 之前，避免负因子被误标为除权日。
    neg_mask = (splitted[['adj_open', 'adj_high', 'adj_low', 'adj_close']] < 0).any(axis=1)
    if neg_mask.any():
        n_neg = int(neg_mask.sum())
        logger.warning(f"  {code}: 检测到 {n_neg} 天负后复权价（hfq 异常），回退为原始价")
        for col in ('open', 'high', 'low', 'close'):
            splitted.loc[neg_mask, f'adj_{col}'] = splitted.loc[neg_mask, f'raw_{col}']
        splitted.loc[neg_mask, 'adj_factor'] = 1.0
    # 孤立未复权错价拦截（协作单 32.0）：剔除 Adj Close≈Close 导致相对相邻因子孤立断崖的行
    _splitted, _n_notch = _guard_unadjusted_notches(splitted)
    if _n_notch > 0:
        logger.warning(f"  {code}: 已剔除 {_n_notch} 天孤立未复权错价行，防复发")
        splitted = _splitted
    if splitted.empty:
        logger.warning(f"  {code}: 全部行均为孤立未复权错价，无可入库数据")
        return None, None
    splitted = detect_factor_dates(splitted)
    splitted['code'] = code

    raw_cols = ['raw_open', 'raw_high', 'raw_low', 'raw_close']
    adj_cols = ['adj_open', 'adj_high', 'adj_low', 'adj_close']

    # ===== 组装 stock_quotes 行（成交价列 = 后复权价）=====
    quotes = pd.DataFrame({
        'code': code,
        'cycle': CYCLE,
        'trade_date': pd.to_datetime(splitted['trade_date']).dt.date,
        # 成交价列统一存后复权价（指标/回测/前端用 adj_close 口径）
        'open': splitted['adj_open'],
        'high': splitted['adj_high'],
        'low': splitted['adj_low'],
        'close': splitted['adj_close'],
        'pre_close': splitted['adj_close'].shift(1),
        'volume': pd.to_numeric(splitted['volume'], errors='coerce').fillna(0).astype(int),
        'amount': (splitted['adj_close'] * pd.to_numeric(splitted['volume'], errors='coerce').fillna(0)).round(2),
        'adjust_type': ADJUST_TYPE,
        'trade_datetime': (
            # 先转纯日期，再拼收盘时间并本地化为港股时区（规避 Yahoo 索引自带时区导致 tz_localize 报错）
            pd.to_datetime(pd.to_datetime(splitted['trade_date']).dt.date)
            + pd.Timedelta(MARKET_CLOSE_HHMM)
        ).dt.tz_localize(HOT),
        'market': MARKET,
    })
    for c in raw_cols:
        quotes[c] = splitted[c]
    for c in adj_cols:
        quotes[c] = splitted[c]
    # 首日无前收：用当日 open（adj）兜底
    quotes.loc[pd.isna(quotes['pre_close']), 'pre_close'] = quotes['open']
    quotes = quotes.dropna(subset=['open', 'close']).reset_index(drop=True)

    # ===== 组装 stock_adj_factor 行（仅除权因子日）=====
    factor_rows = splitted[pd.notna(splitted['factor_date'])].copy()
    if not factor_rows.empty:
        adj_factor = pd.DataFrame({
            'code': code,
            'trade_date': pd.to_datetime(factor_rows['trade_date']).dt.date,
            'adj_factor': factor_rows['adj_factor'],
            'factor_date': pd.to_datetime(factor_rows['factor_date']).dt.date,
            'market': MARKET,
        })
    else:
        adj_factor = pd.DataFrame(columns=['code', 'trade_date', 'adj_factor', 'factor_date', 'market'])

    return quotes, adj_factor


# ==================== 写入方法 ====================
def write_quotes_cols() -> List[str]:
    """stock_quotes 写入列及顺序（write_quotes 与批量快照 _snapshot_quotes_df 共用）。"""
    return ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
            'volume', 'amount', 'adjust_type', 'trade_datetime', 'market',
            'raw_open', 'raw_high', 'raw_low', 'raw_close',
            'adj_open', 'adj_high', 'adj_low', 'adj_close']


def _is_missing(v: Any) -> bool:
    """是否是缺失值（None / pd.NA / NaN），用于批量快照单元格容错。"""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _to_nonneg_int(v: Any) -> Optional[int]:
    """把批量快照成交量等单元格安全转非负 int；空/无效/负值返回 None。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(f) or f < 0:
        return None
    return int(f)


def write_quotes(conn: psycopg2.extensions.connection, df: pd.DataFrame, code: str) -> int:
    """批量写入 stock_quotes（execute_values + ON CONFLICT (code, cycle, trade_date)）。"""
    if df is None or df.empty:
        return 0
    cols = write_quotes_cols()
    values = [tuple(r[c] for c in cols) for r in df[cols].to_dict('records')]
    try:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO stock_quotes (
                    code, cycle, trade_date, open, high, low, close, pre_close,
                    volume, amount, adjust_type, trade_datetime, market,
                    raw_open, raw_high, raw_low, raw_close,
                    adj_open, adj_high, adj_low, adj_close
                ) VALUES %s
                ON CONFLICT (code, cycle, trade_date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    pre_close = EXCLUDED.pre_close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    adjust_type = EXCLUDED.adjust_type,
                    trade_datetime = EXCLUDED.trade_datetime,
                    market = EXCLUDED.market,
                    raw_open = EXCLUDED.raw_open,
                    raw_high = EXCLUDED.raw_high,
                    raw_low = EXCLUDED.raw_low,
                    raw_close = EXCLUDED.raw_close,
                    adj_open = EXCLUDED.adj_open,
                    adj_high = EXCLUDED.adj_high,
                    adj_low = EXCLUDED.adj_low,
                    adj_close = EXCLUDED.adj_close
            """, values, page_size=2000)
        conn.commit()
        logger.info(f"  {code}: 写入 stock_quotes {len(values)} 条")
        return len(values)
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"  {code}: 写入 stock_quotes 失败: {e}")
        raise


def write_adj_factor(conn: psycopg2.extensions.connection, df: pd.DataFrame, code: str) -> int:
    """批量写入 stock_adj_factor（ON CONFLICT (market, code, trade_date)）。"""
    if df is None or df.empty:
        return 0
    cols = ['code', 'trade_date', 'adj_factor', 'factor_date', 'market']
    values = [tuple(r[c] for c in cols) for r in df[cols].to_dict('records')]
    try:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO stock_adj_factor (code, trade_date, adj_factor, factor_date, market)
                VALUES %s
                ON CONFLICT (market, code, trade_date) DO UPDATE SET
                    adj_factor = EXCLUDED.adj_factor,
                    factor_date = EXCLUDED.factor_date
            """, values, page_size=2000)
        conn.commit()
        logger.info(f"  {code}: 写入 stock_adj_factor {len(values)} 条（除权因子日）")
        return len(values)
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"  {code}: 写入 stock_adj_factor 失败: {e}")
        raise


def _list_hk_codes(conn: psycopg2.extensions.connection) -> List[str]:
    """从 stock_basic 取 market='hk' 的代码列表。"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM stock_basic WHERE market = %s ORDER BY code", (MARKET,))
            return [r[0] for r in cur.fetchall()]
    except psycopg2.DatabaseError as e:
        logger.error(f"❌ 查询港股代码列表失败: {e}")
        return []


# ==================== 单标导入 ====================
def import_one(
    src: AkShareDataSource,
    conn: Optional[psycopg2.extensions.connection],
    code: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: Optional[str] = None,
    dry_run: bool = False,
) -> Tuple[int, int, Optional[str]]:
    """拉取并写入单只港股日线 + 复权因子。

    Args:
        src: AkShare 数据源适配器
        conn: 数据库连接（dry_run 时可为 None）
        code: 规范化港股代码（如 0700.HK）
        start/end: 日期区间（YYYY-MM-DD）
        period: 或指定拉取周期（忽略，AkShare 全量后切片）
        dry_run: 试运行模式，拉取并打印、不落库

    Returns:
        (quotes 条数, adj_factor 条数, 实际覆盖的最后交易日 ISO 字符串)
    """
    df_raw = src.download_single(code, market=MARKET, start=start, end=end, period=period)
    if df_raw is None or df_raw.empty:
        logger.info(f"  {code}: 拉取为空（可能限流或停牌）")
        return 0, 0, None

    quotes, adj_factor = clean_and_split(df_raw, code)
    q = 0 if quotes is None else len(quotes)
    a = 0 if adj_factor is None else len(adj_factor)
    max_date: Optional[str] = None
    if quotes is not None and not quotes.empty:
        max_date = pd.to_datetime(quotes['trade_date']).max().date().isoformat()
    if dry_run:
        logger.info(f"[DRY-RUN] {code}: 待写入 quotes {q} 条, adj_factor {a} 条")
        if quotes is not None and not quotes.empty:
            logger.info(quotes.tail(3).to_string(index=False))
        return q, a, max_date

    if conn is None:
        raise RuntimeError('非 dry-run 模式必须提供数据库连接')
    q = write_quotes(conn, quotes, code) if quotes is not None else 0
    a = write_adj_factor(conn, adj_factor, code) if adj_factor is not None else 0
    return q, a, max_date


def resolve_one(conn: psycopg2.extensions.connection, src: AkShareDataSource,
                code: str, dry_run: bool = False) -> Tuple[int, int, Optional[str]]:
    """按「当日单日」窗口回退拉取并写入单只港股（供批量快照对除权/新股回退）。

    等价于 import_one 的当日窗口版本：拉取该股当日不复权+后复权日线，经 clean_and_split
    拆分后写入 stock_quotes / stock_adj_factor（含除权检测），与逐只路径口径完全一致。

    Args:
        conn: 数据库连接（dry_run 时可为 None）
        src: AkShare 数据源适配器（需为 hk）
        code: 规范化港股代码（如 0700.HK）
        dry_run: 试运行模式（拉取打印、不落库）

    Returns:
        (quotes 条数, adj_factor 条数, 实际覆盖的最后交易日 ISO 字符串)
    """
    today = date.today()
    start = today.isoformat()
    end_excl = (today + timedelta(days=1)).isoformat()
    df_raw = src.download_single(code, market=MARKET, start=start, end=end_excl)
    if df_raw is None or df_raw.empty:
        logger.info(f"  {code}: 快照回退拉取为空（可能退市/停牌/限流）")
        return 0, 0, None
    quotes, adj_factor = clean_and_split(df_raw, code)
    q = 0 if quotes is None else len(quotes)
    a = 0 if adj_factor is None else len(adj_factor)
    max_date: Optional[str] = None
    if quotes is not None and not quotes.empty:
        max_date = pd.to_datetime(quotes['trade_date']).max().date().isoformat()
    if dry_run:
        logger.info(f"[DRY-RUN] {code}: 回退待写入 quotes {q} 条, adj_factor {a} 条")
        return q, a, max_date
    if conn is None:
        raise RuntimeError('非 dry-run 模式必须提供数据库连接')
    qq = write_quotes(conn, quotes, code) if quotes is not None else 0
    aa = write_adj_factor(conn, adj_factor, code) if adj_factor is not None else 0
    return qq, aa, max_date


def _hk_snapshot_latest(conn: psycopg2.extensions.connection, code: str,
                        before_date: Optional[date] = None) -> Optional[Tuple[float, float]]:
    """读取港股该股最近一笔（默认）或某交易日**之前**最近一笔已入库 (adj_close, raw_close)。

    用于批量快照：`adj_close/raw_close` 为后复权倍率 C（把无复权快照换算为后复权价），
    raw_close 用于除权疑似检测（与新浪快照「昨收」比较）。
    库中无有效锚点（新上市/缺 raw_close）时返回 None，由调用方回退逐只下载。

    Args:
        conn: psycopg2 连接
        code: 规范化港股代码（如 0700.HK）
        before_date: 若给定，只取 < before_date 的最新一笔（即快照交易日 T 之前的 T-1），
            用于批量快照场景——此时快照「昨收」正是 T-1 收盘，应与 T-1 的 raw_close 对齐；
            否则（库中恰为 T）会把 T 自身当锚点、昨收对 T 误判为除权。

    Returns:
        (最近 adj_close, 最近 raw_close)；无有效锚点返回 None
    """
    before_clause = "AND trade_date < %s" if before_date is not None else ""
    params: List[Any] = [code]
    if before_date is not None:
        params.append(before_date)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT adj_close, raw_close FROM stock_quotes "
                "WHERE market='hk' AND code=%s AND cycle='1d' "
                "AND adj_close IS NOT NULL AND raw_close IS NOT NULL AND raw_close > 0 "
                f"AND adj_close > 0 {before_clause} ORDER BY trade_date DESC LIMIT 1",
                tuple(params),
            )
            row = cur.fetchone()
        if row and row[0] and row[1]:
            return float(row[0]), float(row[1])
    except psycopg2.DatabaseError as e:
        logger.warning(f"⚠️ 读取港股 {code} 复权锚点失败: {e}")
    return None


def _hk_rate_diverges(spot_prev: Optional[float], raw_close: Optional[float]) -> bool:
    """除权疑似检测：新浪快照「昨收」与库中 T-1 的 raw_close 明显偏离时判定疑似除权。

    批量快照无复权因子，若该股当日除权（价格跳空），直接用 T-1 锚点换算会得到错误的后复权价。
    正常交易日快照「昨收」应等于库中 T-1 的 raw_close（二者都是前一日收盘，原始价口径）。
    阈值取 2%：兼顾两相——
    - 净例噪声：低价仙股昨收与库中 raw_close 常因四舍五入/tick 差 0.5%~1.5%（如 0.66 vs 0.665），
      0.5% 会被大量误判回退使批量加速失效，故放宽；
    - 真实除权（分红/送股）跳空通常在 2% 以上，2% 阈值仍能拦截明显除权。
    极端小比例除权（<2%）存在以 T-1 锚点误换算的泄露风险，但影响极小、且 resolve_one
    仍对「昨收缺失」等不确定情形保守回退，总体安全。
    > 注：自「权威除权路由」接入后，港交所当日除净名单命中的股票已在 _hk_exright_codes
    > 处**无条件回退逐只**，本启发式仅作为港交所名单拉取失败（返回 None）时的兜底。

    Args:
        spot_prev: 快照昨收（新浪 stock_hk_spot 的「昨收」，原始价口径）
        raw_close: 库中 T-1 的 raw_close（昨日原始收盘）

    Returns:
        True=疑似除权应回退，False=可安全批量换算
    """
    if spot_prev is None or raw_close is None or raw_close <= 0:
        # 缺昨收/缺库中昨日收盘的无法判断，保守回退
        return True
    ratio = spot_prev / raw_close
    return abs(ratio - 1.0) > 0.02


def _hk_exright_codes(trade_date: date) -> Optional[set]:
    """拉取港交所官方「Dividends & Other Entitlements」全市场除权除息名单，返回当日除净日命中代码集。

    作为批量快照路径的**权威除权路由**数据源：港交所在一个页面列出全部上市发行人当前有效的
    除权除息登记，含 Ex-Date（除净日/除息日）列。当日除净日命中的股票批量快照无法正确换算后复权
    （T-1 锚点法在除权后失效），须无条件回退逐只下载。

    Args:
        trade_date: 目标交易日（批量快照的交易日期），按「除净日 = trade_date」过滤命中。

    Returns:
        命中的港股代码集（规范形如 '0700.HK'，零填充 4 位）；拉取/解析/匹配失败返回 None，
        此时调用方回落启发式 `_hk_rate_diverges` 判定。
    """
    # 港交所 Ex-Date 为 dd/mm（日/月）格式（如 "30/05"=5月30日）
    want_md = f"{trade_date.day:02d}/{trade_date.month:02d}"
    try:
        resp = requests.get(
            HKEX_EENT_URL,
            timeout=20,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; hk-daily-importer)'},
        )
        resp.raise_for_status()
        import io

        tables = pd.read_html(io.StringIO(resp.text))
        data = next((t for t in tables if t.shape[1] >= 6), None)
        if data is None:
            logger.warning('⚠️ 港交所除权名单表格结构异常，回落启发式检测')
            return None

        codes: set = set()
        for _, row in data.iterrows():
            name_cell = row.get(1)
            ex_cell = row.get(4)
            if not isinstance(name_cell, str) or not isinstance(ex_cell, str):
                continue
            ex_block = ex_cell.strip()
            if not ex_block:
                continue
            match_code = re.search(r'\((\d{1,5})\)', name_cell)
            if not match_code:
                continue
            # 港交所码位 1~5 位变长显示（如 Tencent (00700)→0700.HK）；
            # 复用 normalize_code 保证与 stock_quotes 库内代码口径一致。
            code = normalize_code(match_code.group(1), 'hk')
            # Ex-Date 形如 "31/08" 或 "31/08/2026"，取前两段 dd/mm 与目标交易日比对
            parts = ex_block.split('/')
            if len(parts) < 2:
                continue
            md = f"{parts[0].strip().zfill(2)}/{parts[1].strip().zfill(2)}"
            if md == want_md:
                codes.add(code)
        logger.info(f"📖 港交所权威除权名单：{trade_date} 共 {len(codes)} 只除净")
        return codes
    except Exception as e:
        logger.warning(f"⚠️ 港交所除权名单拉取/解析失败（回落启发式）: {e}")
        return None


def _snapshot_quotes_df(code: str, r: pd.Series, anchor: float, trade_date: date) -> pd.DataFrame:
    """把批量快照单行（原始价）+ 复权锚点 C 构造为入库的 stock_quotes 单日 DataFrame。

    成交价列统一存后复权价 = 原始价 × C（与逐只路径 clean_and_split 口径一致）；同时存
    raw_*/adj_*。pre_close=库中最近后复权价（= raw_close×C），保证序列连续。

    Args:
        code: 规范化港股代码
        r: 快照行（Column Open/High/Low/Close/prev_close/Volume/Amount）
        anchor: 复权倍率 C = 最近 adj_close/raw_close
        trade_date: 当日交易日期

    Returns:
        stock_quotes 单行 DataFrame（与 write_quotes 期望列对齐）
    """
    raw_open = r.get('Open')
    raw_high = r.get('High')
    raw_low = r.get('Low')
    raw_close = r.get('Close')
    raw_prev = r.get('prev_close')
    if _is_missing(raw_open) or _is_missing(raw_close):
        # 无有效成交价（如停牌快照全空）→ 返回空 df，调用方跳过
        return pd.DataFrame(columns=write_quotes_cols())
    vol = _to_nonneg_int(r.get('Volume'))
    C = anchor
    adj_open = raw_open * C if not _is_missing(raw_open) else None
    adj_high = raw_high * C if not _is_missing(raw_high) else None
    adj_low = raw_low * C if not _is_missing(raw_low) else None
    adj_close = raw_close * C
    # pre_close：库中最近后复权价（≈ raw_prev×C）
    prev = raw_prev * C if raw_prev is not None and not _is_missing(raw_prev) else adj_open
    amount = (adj_close * vol) if vol is not None else None
    trade_datetime = (pd.Timestamp(trade_date) + pd.Timedelta(MARKET_CLOSE_HHMM)).tz_localize(HOT)
    row = {
        'code': code, 'cycle': CYCLE, 'trade_date': trade_date,
        'open': adj_open, 'high': adj_high, 'low': adj_low, 'close': adj_close,
        'pre_close': prev, 'volume': vol, 'amount': amount, 'adjust_type': ADJUST_TYPE,
        'trade_datetime': trade_datetime, 'market': MARKET,
        'raw_open': raw_open, 'raw_high': raw_high, 'raw_low': raw_low, 'raw_close': raw_close,
        'adj_open': adj_open, 'adj_high': adj_high, 'adj_low': adj_low, 'adj_close': adj_close,
    }
    return pd.DataFrame([row], columns=write_quotes_cols())


def import_hk_snapshot_daily(conn: psycopg2.extensions.connection, src: AkShareDataSource,
                             dry_run: bool = False) -> int:
    """「当日增量」批量快照导入：一次拉取全市场当日 OHLCV，锚定库中后复权序列换算写入。

    仅在增量窗口只含最新单日时调用（见 run_incremental）。对无复权锚点（新股）或疑似除权
    （昨收与库中最近 raw_close 偏离）的股票，静默回退 `resolve_one` 逐只拉取，保证复权口径不被破坏。

    Args:
        conn: 数据库连接（dry_run 时可为 None；批量换算需穿库取锚点）
        src: AkShare 数据源适配器
        dry_run: 试运行模式（拉取打印、不落库）

    Returns:
        dict：{snap_ok: 快照是否成功拉取, direct: 直写数, fallback: 回退数, failed: 失败数}
        snap_ok=False（快照接口失败/空）时 run_incremental 应沿用逐只路径。
    """
    snap = src.download_hk_snapshot_all()
    if snap is None or snap.empty:
        logger.warning('⚠️ 批量快照拉取为空/失败，跳过（将回落原逐只增量路径）')
        return {'snap_ok': False, 'direct': 0, 'fallback': 0, 'failed': 0}

    direct, fallback, failed, exright = 0, 0, 0, 0
    quotes_rows: Dict[str, pd.DataFrame] = {}
    # 当日交易日期 = 快照索引（单日）
    snap_date = snap.index.max().date()
    logger.info(f"📸 批量快照：拉取港股全市场 {len(snap)} 只当日快照，交易日 {snap_date}")

    # 权威除权路由：港交所当日除净名单（单请求全市场）。拉取失败返回 None → 回落启发式。
    exright_codes = _hk_exright_codes(snap_date)

    for _, r in snap.iterrows():
        # 快照 df 以交易日期为索引，code 存于列中
        code = str(r.get('code', '')).strip()
        if not code:
            continue
        try:
            # 权威名单命中 → 无条件回退逐只（批量 T-1 锚点法在除权日失效）
            if exright_codes is not None and code in exright_codes:
                logger.info(f"  {code}: 港交所名单命中（当日除净）→ 回退逐只")
                exright += 1
                fallback += 1
                if not dry_run:
                    resolve_one(conn, src, code, dry_run=False)
                continue
            if conn is None or dry_run:
                # dry-run/无连库无法取锚点：保守回退逐只（dry-run 下不调用 resolve_one 落库）
                fallback += 1
                if not dry_run:
                    resolve_one(conn, src, code, dry_run=False)
                continue
            latest = _hk_snapshot_latest(conn, code, snap_date)
            if latest is None:
                # 新上市/缺历史 → 回退逐只完整拉取（含复权检测）
                fallback += 1
                resolve_one(conn, src, code, dry_run=False)
                continue
            adj_close, raw_close = latest
            anchor = adj_close / raw_close
            # 除权疑似检测：快照昨收 与 库中最近 raw_close 比较
            if _hk_rate_diverges(r.get('prev_close'), raw_close):
                logger.info(f"  {code}: 快照昨收 {r.get('prev_close')} vs 库最近 raw_close {raw_close} 偏离，疑似除权 → 回退逐只")
                fallback += 1
                resolve_one(conn, src, code, dry_run=False)
                continue
            quotes = _snapshot_quotes_df(code, r, anchor, snap_date)
            if quotes is None or quotes.empty:
                fallback += 1  # 无有效价（停牌）→ 回退逐只尝试
                resolve_one(conn, src, code, dry_run=False)
                continue
            quotes_rows[code] = quotes
            direct += 1
        except Exception as e:
            failed += 1
            logger.error(f"  {code}: 批量快照处理失败: {e}")
            try:
                resolve_one(conn, src, code, dry_run=False)
            except Exception as e2:
                logger.error(f"  {code}: 回退也失败: {e2}")
    if failed:
        logger.warning(f"⚠️ 批量快照处理失败 {failed} 只（已尝试回退）")

    if not dry_run:
        for code, quotes in quotes_rows.items():
            try:
                write_quotes(conn, quotes, code)
            except psycopg2.Error as e:
                failed += 1
                logger.error(f"  {code}: 批量写入失败: {e}")
    logger.info(f"✅ 批量快照完成: 直写 {direct}, 回退 {fallback}（含权威除权 {exright}）, 失败 {failed}")
    return {'snap_ok': True, 'direct': direct, 'fallback': fallback, 'failed': failed, 'exright': exright}


def run_init(src: AkShareDataSource, conn: psycopg2.extensions.connection,
             limit: Optional[int] = None, dry_run: bool = False,
             start_date: Optional[str] = None) -> Dict[str, int]:
    """全量导入（默认 period='max'；指定 start_date 时按 [start_date, 今天] 区间拉取）。

    支持限流与断点续传。Returns: 统计 dict。

    Args:
        src: AkShare 数据源适配器
        conn: 数据库连接（dry_run 时可为 None）
        limit: 仅处理前 N 只（调试用）
        dry_run: 试运行模式，不落库
        start_date: 起始日期（YYYY-MM-DD）；给定则替代全量 period，按区间下载
    """
    codes = _list_hk_codes(conn) if not dry_run else []
    if dry_run:
        # dry-run 下未从库读取代码，用一份小样例验证流程
        codes = ['9988.HK', '700.HK']
    if limit:
        codes = codes[:limit]
    cfg = src.cfg
    # 断点续传：加载游标，跳过已处理的标的
    if not dry_run:
        last_proc = get_market_last_processed_code(conn, MARKET)
        if last_proc:
            before = len(codes)
            codes = resume_codes(codes, last_proc)
            logger.info(f"🔁 断点续传：上次处理至 {last_proc}，跳过 {before - len(codes)} 只，剩余 {len(codes)} 只")
    stats = {'quotes': 0, 'adj_factor': 0, 'success': 0, 'fail': 0, 'max_trade_date': None}
    if start_date:
        end = date.today().isoformat()
        logger.info(f"🚀 [init] 区间导入 {len(codes)} 只港股，{start_date} ~ {end}")
    else:
        end = None
        logger.info(f"🚀 [init] 全量导入 {len(codes)} 只港股（period={cfg.default_period}）")
    for i, code in enumerate(codes, 1):
        try:
            if start_date:
                q, a, max_date = import_one(src, conn if not dry_run else None, code,
                                            start=start_date, end=end, dry_run=dry_run)
            else:
                q, a, max_date = import_one(src, conn if not dry_run else None, code,
                                            period=cfg.default_period, dry_run=dry_run)
            if q or a:
                stats['success'] += 1
                stats['quotes'] += q
                stats['adj_factor'] += a
                if max_date and (stats['max_trade_date'] is None or max_date > stats['max_trade_date']):
                    stats['max_trade_date'] = max_date
            else:
                stats['fail'] += 1
        except Exception as e:
            stats['fail'] += 1
            logger.error(f"  {code}: 导入失败: {e}")
        # 限流：每个标处理后随机休眠，降低数据源请求频率（防「拉取为空」限流）
        rate_limit_sleep(cfg)
        # 断点续传：回写当前已处理游标（中断后可从其之后继续）
        if not dry_run:
            set_market_last_processed_code(conn, MARKET, code)
        if i % 50 == 0:
            logger.info(f"  进度 {i}/{len(codes)}")
    if not dry_run:
        # 整批遍历完，清空游标（本轮目标已处理完，下次运行重新从 batch 起点续日期窗口）
        set_market_last_processed_code(conn, MARKET, None)
        # 仅在成功写入时才回写：避免全量失败轮次把 last_sync_date 推进、吞掉缺口
        if stats['quotes'] > 0:
            write_back = stats['max_trade_date'] or date.today().isoformat()
            set_last_sync_date(conn, write_back)
            logger.info(f"📝 本轮成功写入 {stats['quotes']} 条，last_sync_date 回写至 {write_back}")
        else:
            logger.warning('⚠️ 本轮无成功写入，跳过回写 last_sync_date（保留旧进度，下次可重试）')
    logger.info(f"✅ init 完成: 成功 {stats['success']}, 失败 {stats['fail']}, "
                f"quotes {stats['quotes']}, adj_factor {stats['adj_factor']}")
    return stats


def _probe_src_latest(src: AkShareDataSource, end: str) -> str:
    """探测数据源实际最新交易日，作为增量窗口终点（不超过 end）。

    生产港股**当日增量**的数据路径为批量快照源 `download_hk_snapshot_all`
    （ak.stock_hk_spot，一次全市场当日 OHLCV，前一交易日 17:02 前后即就绪），
    而新浪**逐只日线**接口通常滞后一天（例如 09-09 探测 0700.HK 仍返回 09-08）。
    若继续用逐只日线探测，会把 09-09 误判为"数据源未更新"而整批跳过当日导入。

    故此处改用批量快照源探测最新交易日：快照非空且已覆盖当日时返回 end，否则降级。
    若早于 end 则降级窗口终点；数据源更新后重跑自动补回缺口。

    Args:
        src: AkShare 数据源适配器
        end: 期望窗口终点（通常是今天）

    Returns:
        实际窗口终点（min(end, 数据源最新交易日)）；探针失败时保守沿用 end。
    """
    snap = src.download_hk_snapshot_all()
    if snap is None or getattr(snap, 'empty', True) \
            or snap.index.max() is None or pd.isna(snap.index.max()):
        logger.warning("⚠️ 批量快照探针不可用，无法探测最新日期，沿用窗口终点 "
                       f"{end}")
        return end
    latest_str = pd.to_datetime(snap.index.max()).date().isoformat()
    if latest_str < end:
        logger.warning(f"⚠️ 数据源最新日期 {latest_str}（批量快照）早于今天 {end}，"
                       f"增量窗口终点调整为 {latest_str}；数据源更新后重跑可补回缺口")
        return latest_str
    return end


def _window_is_single_day(src: AkShareDataSource, start: str, end: str) -> bool:
    """批量快照可用性判定：增量窗口是否仅覆盖最新单交易日 `end`。

    ak.stock_hk_spot() 只返回最新一天快照，故仅当窗口内除最新交易日外没有任何其他
    交易日（即 last_sync 到数据源最新之间无待补缺口）时才启用批量路径；若期间跨了
    交易日但未同步（存在缺口），必须回退逐只拉取，避免静默跳过中间交易日造成数据缺口。

    统一以批量快照源判定（与生产路径一致，逐只日线源滞后一天不可用）：
    - 快照最新交易日 == end，且 [start, end) 内不含工作日（仅周末/节假日可跳过）→ 启用批量
    - 快照不可用 / 最新日 ≠ end / 窗口内存在工作日缺口 → 保守逐只

    Args:
        src: AkShare 数据源适配器
        start: 增量起点（YYYY-MM-DD，上轮 last_sync_date+1 或回溯兜底）
        end: 数据源最新交易日（YYYY-MM-DD）

    Returns:
        是否可在本窗口启用批量快照快速对齐
    """
    snap = src.download_hk_snapshot_all()
    if snap is None or getattr(snap, 'empty', True) \
            or snap.index.max() is None or pd.isna(snap.index.max()):
        logger.warning("⚠️ 批量窗口判定探针不可用，保守沿用逐只增量路径")
        return False
    latest = pd.to_datetime(snap.index.max()).date().strftime('%Y-%m-%d')
    if latest != end:
        logger.warning(f"⚠️ 批量快照最新交易日 {latest} ≠ 窗口终点 {end}，"
                       f"需要补历史缺口，沿用逐只增量路径")
        return False
    s = datetime.strptime(start, '%Y-%m-%d').date()
    e = datetime.strptime(end, '%Y-%m-%d').date()
    # [start, end) 内存在工作日 → 有交易日缺口，必须逐只补全
    has_weekday = any((s + timedelta(days=i)).weekday() < 5
                      for i in range(max(0, (e - s).days)))
    if has_weekday:
        logger.warning(f"⚠️ 增量窗口 {start}~{end} 内存在工作日（需补历史缺口），"
                       f"沿用逐只增量路径")
        return False
    logger.info(f"⚡ 批量快照已覆盖最新交易日 {latest} 且窗口内无待补缺口，可启用批量快照")
    return True


def run_incremental(src: AkShareDataSource, conn: psycopg2.extensions.connection,
                    limit: Optional[int] = None, dry_run: bool = False) -> Dict[str, int]:
    """增量导入（从 etl_control.last_sync_date+1 到今天）。Returns: 统计 dict。"""
    today = date.today().isoformat()
    # 探测数据源实际最新交易日：新浪港股日线收盘后延迟更新，仍以 date.today() 为终点
    # 会整批「拉取为空」空跑，故降级为数据源最新日期（探针失败时保守沿用 today）。
    end = _probe_src_latest(src, today)
    last_str = get_last_sync_date(conn) if not dry_run else None
    if last_str:
        start = (datetime.strptime(last_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        # 无增量起点：回溯兜底窗口（MarketConfig.incremental_lookback_days=7）
        start = (date.today() - timedelta(days=src.cfg.incremental_lookback_days)).isoformat()
        logger.info(f"📅 etl_control 无记录，回溯 {src.cfg.incremental_lookback_days} 天作为起点")

    if start > end:
        logger.warning(f"⚠️ 数据源最新日期 {end} 尚未覆盖增量起点 {start}，本轮无新增数据可拉，跳过")
        return {'quotes': 0, 'adj_factor': 0, 'success': 0, 'fail': 0, 'max_trade_date': None}

    # 新浪切片为半开区间 [start, end)（不含 end），终点 +1 天以包含数据源最新交易日 end 当天
    end_excl = (datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    codes = _list_hk_codes(conn) if not dry_run else ['700.HK']
    if limit:
        codes = codes[:limit]

    cfg = src.cfg
    # 断点续传：加载游标，跳过已处理的标的
    if not dry_run:
        last_proc = get_market_last_processed_code(conn, MARKET)
        if last_proc:
            before = len(codes)
            codes = resume_codes(codes, last_proc)
            logger.info(f"🔁 断点续传：上次处理至 {last_proc}，跳过 {before - len(codes)} 只，剩余 {len(codes)} 只")

    stats = {'quotes': 0, 'adj_factor': 0, 'success': 0, 'fail': 0, 'max_trade_date': None}
    logger.info(f"🚀 [incremental] 增量导入 {len(codes)} 只港股，区间 {start} ~ {end}")

    # ===== 批量快照加速（当日单日快速对齐）=====
    # ak.stock_hk_spot() 一次返回全市场当日快照，可把逐只 2802 次请求压缩为 1 次；
    # 但快照仅覆盖最新交易单日，故仅当增量窗口只含最新交易日（无待补缺口）时启用，
    # 否则必须沿用逐只路径，避免静默跳过中间交易日造成数据缺口。
    if not dry_run and limit is None and _window_is_single_day(src, start, end):
        batch = import_hk_snapshot_daily(conn, src, dry_run=False)
        if batch['snap_ok']:
            # 快照已拉取：direct 为快照直写、fallback 为其内部已用 resolve_one 回退落库，
            # 二者都已覆盖最新单日 → 整批对齐完成，无需再走逐只循环。
            covered = batch['direct'] + batch['fallback']
            logger.info(f"✅ 批量快照对齐完成: 直写 {batch['direct']}, "
                        f"内部回退 {batch['fallback']}, 覆盖 {covered} 只")
            if batch['direct'] > 0:
                stats['success'] += batch['direct'] + batch['fallback']
                stats['quotes'] += batch['direct']
            stats['max_trade_date'] = end
            # 整批处理完，清断点游标并回写增量进度至数据源最新交易日
            set_market_last_processed_code(conn, MARKET, None)
            if stats['quotes'] > 0:
                set_last_sync_date(conn, end)
                logger.info(f"📝 批量快照对齐后 last_sync_date 回写至 {end}")
            else:
                logger.warning('⚠️ 批量快照直写为空（全部回退亦无价），保留原 last_sync_date')
            logger.info(f"✅ incremental(批量) 完成: 直写 {batch['direct']}")
            return stats
        logger.warning('⚡ 批量快照接口未返回数据，回退逐只增量路径')

    for i, code in enumerate(codes, 1):
        try:
            q, a, max_date = import_one(src, conn if not dry_run else None, code, start=start, end=end_excl, dry_run=dry_run)
            if q or a:
                stats['success'] += 1
                stats['quotes'] += q
                stats['adj_factor'] += a
                if max_date and (stats['max_trade_date'] is None or max_date > stats['max_trade_date']):
                    stats['max_trade_date'] = max_date
            else:
                stats['fail'] += 1
        except Exception as e:
            stats['fail'] += 1
            logger.error(f"  {code}: 导入失败: {e}")
        # 限流：每个标处理后随机休眠，降低数据源请求频率（防「拉取为空」限流）
        rate_limit_sleep(cfg)
        # 断点续传：回写当前已处理游标（中断后可从其之后继续）
        if not dry_run:
            set_market_last_processed_code(conn, MARKET, code)
        if i % 50 == 0:
            logger.info(f"  进度 {i}/{len(codes)}")
    if not dry_run:
        # 整批遍历完，清空游标（本轮目标已处理完，下次运行重新从 batch 起点续日期窗口）
        set_market_last_processed_code(conn, MARKET, None)
        # 仅在成功写入时才回写，且回写【实际覆盖的最后交易日】而非 date.today()：
        # 1) 失败轮次不回写，保留旧进度，下次增量可重试补缺口；
        # 2) 盘中/盘前未收盘时拉到的是前一交易日数据，回写实际覆盖日，避免把未来日期推进为已同步。
        if stats['quotes'] > 0:
            write_back = stats['max_trade_date'] or today
            set_last_sync_date(conn, write_back)
            logger.info(f"📝 本轮成功写入 {stats['quotes']} 条，last_sync_date 回写至 {write_back}")
        else:
            logger.warning('⚠️ 本轮无成功写入，跳过回写 last_sync_date（保留旧进度，下次增量可重试补缺口）')
    logger.info(f"✅ incremental 完成: 成功 {stats['success']}, 失败 {stats['fail']}, "
                f"quotes {stats['quotes']}, adj_factor {stats['adj_factor']}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description='港股日线行情下载脚本')
    parser.add_argument('--init', action='store_true', help='全量导入（period=max）')
    parser.add_argument('--start-date', type=str, default=None,
                        help='与 --init 联用：按 [起始日期, 今天] 区间导入（如 2025-01-01），替代全量 period')
    parser.add_argument('--incremental', action='store_true', help='增量导入（last_sync_date+1~今天）')
    parser.add_argument('--limit', type=int, default=None, help='最多拉取的标的数量（调试用）')
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（拉取验证、不落库）')
    parser.add_argument('--test-one', type=str, default=None, help='拉取单只验证（如 9988.HK）')
    args = parser.parse_args()

    if not (args.init or args.incremental or args.test_one):
        parser.error('请指定 --init / --incremental / --test-one 之一')

    src = AkShareDataSource(market=MARKET)
    if not src.connect():
        logger.error('❌ AkShare 数据源连接失败')
        raise SystemExit(1)

    conn = None
    try:
        if args.dry_run:
            conn = None
        else:
            conn = _connect()

        if args.test_one:
            code = normalize_code(args.test_one, MARKET)
            start = (date.today() - timedelta(days=5 * 365)).isoformat()
            logger.info(f"🎯 单只验证: {code}（区间 {start} ~ 今天）")
            q, a, _ = import_one(src, conn, code, start=start, dry_run=args.dry_run)
            logger.info(f"🎯 {code} 完成: quotes {q} 条, adj_factor {a} 条")
        elif args.init:
            run_init(src, conn, limit=args.limit, dry_run=args.dry_run, start_date=args.start_date)
        elif args.incremental:
            run_incremental(src, conn, limit=args.limit, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f'程序异常: {e}')
        raise
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    main()