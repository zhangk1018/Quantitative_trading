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
import sys
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
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
PROBE_CODE = '0700.HK'         # 增量窗口探针标的：腾讯，恒生权重股几乎每日成交


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
def write_quotes(conn: psycopg2.extensions.connection, df: pd.DataFrame, code: str) -> int:
    """批量写入 stock_quotes（execute_values + ON CONFLICT (code, cycle, trade_date)）。"""
    if df is None or df.empty:
        return 0
    cols = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
            'volume', 'amount', 'adjust_type', 'trade_datetime', 'market',
            'raw_open', 'raw_high', 'raw_low', 'raw_close',
            'adj_open', 'adj_high', 'adj_low', 'adj_close']
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

    新浪港股日线在收盘后延迟更新（港股 16:00 收盘，17:00 调度时当日数据常尚未落地）。
    若增量窗口终点硬编码为 date.today()，数据源未更新时整批「拉取为空」空跑，既浪费时间
    又高频请求新浪接口（易触发限流）。此处以代表股全量历史的最大日期近似数据源最新交易日，
    若早于 end 则降级窗口终点；数据源更新后重跑自动补回缺口。

    Args:
        src: AkShare 数据源适配器
        end: 期望窗口终点（通常是今天）

    Returns:
        实际窗口终点（min(end, 数据源最新交易日)）；探针失败时保守沿用 end。
    """
    df = src.download_single(PROBE_CODE, market=MARKET)
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        logger.warning(f"⚠️ 数据源探针 {PROBE_CODE} 不可用，无法探测最新日期，沿用窗口终点 {end}")
        return end
    latest = df.index.max()
    if latest is None or pd.isna(latest):
        return end
    latest_str = pd.to_datetime(latest).date().isoformat()
    if latest_str < end:
        logger.warning(f"⚠️ 数据源最新日期 {latest_str}（探针 {PROBE_CODE}）早于今天 {end}，"
                       f"增量窗口终点调整为 {latest_str}；数据源更新后重跑可补回缺口")
        return latest_str
    return end


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
    for i, code in enumerate(codes, 1):
        try:
            q, a, max_date = import_one(src, conn if not dry_run else None, code, start=start, end=end, dry_run=dry_run)
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