#!/usr/bin/env python3
"""
周线/月线 K 线聚合计算脚本

从日线('1d')数据聚合生成周线('1w')或月线('1m')K 线，分两条互不干扰的分支：

- **cn（默认）**：沿用 A 股 `trade_calendar` 判定「本周/本月最后一个交易日」，行为与旧版一致，
  并连带写入 `market='index'`（沪深300/上证）。现有 cn plist 不传 `--market`，故零改动。
- **hk / us**：不再依赖 A 股日历，改用**该市场自己的数据源交易日历**（港股 HSI / 美股 .IXIC，
  与 `import_{hk,us}_daily` 的交易日判定同源）划分周期、判定周期是否已结束，聚合范围只含该市场。
  之所以必须如此：A 股休市而港/美开市的日子（国庆、中秋等），旧逻辑既不会触发聚合，
  也会把这些日线落在任何周期区间之外 → 永久孤儿。

港/美股分支要点：
- 周期桶：`1w` = ISO 周（周一~周日）；`1m` = 自然月。
- 结算判据：`1w` = 该 ISO 周的周六已到（港/美股周末休市，周六必然晚于该周全部可能交易日）；
  `1m` = 自然月末已到。真实交易日仍完全取自数据源日历，此判据只决定「何时可结算」。
- 完整度门禁：该桶内**该市场每个交易日**都必须已落库 1d 数据，否则跳过（宁缺勿残，待下次自愈）。
- 先删后插：按桶的自然日跨度删除该市场旧行再写入，保证一个周期只有一条；
  每次运行重算最近 N 个周期，迟到/修正的数据会在下次运行被自动吸收。
- 交易日历不可用（数据源返回 None）时只告警跳过，绝不猜测。

用法:
    # 沪深（等价旧版行为；现有 cn 的 weekly/monthly plist 走此分支）
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1w
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1m

    # 港/美股（独立 launchd：周二~六 09:30 周K / 10:00 月K）
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1w --market hk,us
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1m --market hk,us

    # 历史回填（--rebuild：遍历区间内全部周期桶，仍遵守「齐备才写」）
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1w --market hk --rebuild --from 2025-01-01
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1m --market us --rebuild --from 2025-01-01

    # 沪深指定日期回算 / 港美股「视作某日运行」（便于验证）
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1w --date 2026-08-07
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1w --market hk --date 2026-10-03
"""
import os
import sys
import json
import argparse
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.logger import setup_logger

logger = setup_logger('bar_aggregation')

# ===================== 数据库连接 =====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))

OVERSEAS_MARKETS = {'hk', 'us'}
# 正常运行回看的周期桶数量（吸收迟到/修正数据）：周线最近 4 周、月线最近 3 个月。
DEFAULT_LOOKBACK = {'1w': 4, '1m': 3}

# 沪深聚合：market 过滤写死，避免再顺带把港/美股写进 A 股口径（index = 沪深300/上证）
CN_AGG_SQL = """
    INSERT INTO stock_quotes (code, cycle, trade_date, open, high, low, close,
                               volume, amount, adjust_type, trade_datetime, pre_close, ah_vol, ah_amount,
                               market)
    SELECT
        q.code,
        '{cycle}' AS cycle,
        %s AS trade_date,
        (ARRAY_AGG(q.open ORDER BY q.trade_date))[1] AS open,
        MAX(q.high) AS high,
        MIN(q.low) AS low,
        (ARRAY_AGG(q.close ORDER BY q.trade_date DESC))[1] AS close,
        SUM(q.volume) AS volume,
        SUM(q.amount) AS amount,
        'qfq' AS adjust_type,
        (%s::date + TIME '15:00:00')::timestamp AT TIME ZONE 'Asia/Shanghai' AS trade_datetime,
        0 AS pre_close,
        0 AS ah_vol,
        0 AS ah_amount,
        MIN(q.market) AS market
    FROM stock_quotes q
    WHERE q.cycle = '1d'
      AND q.market IN ('cn', 'index')
      AND q.trade_date >= %s
      AND q.trade_date <= %s
      AND q.open IS NOT NULL
      AND q.close IS NOT NULL
    GROUP BY q.code
    ON CONFLICT (code, cycle, trade_date, adjust_type) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        pre_close = 0,
        trade_datetime = EXCLUDED.trade_datetime,
        ah_vol = EXCLUDED.ah_vol,
        ah_amount = EXCLUDED.ah_amount,
        market = EXCLUDED.market
"""

# 港/美股聚合：只聚合本市场，market 直接取参数（不再 MIN 推断）
OVERSEAS_AGG_SQL = """
    INSERT INTO stock_quotes (code, cycle, trade_date, open, high, low, close,
                               volume, amount, adjust_type, trade_datetime, pre_close, ah_vol, ah_amount,
                               market)
    SELECT
        q.code,
        %s AS cycle,
        %s AS trade_date,
        (ARRAY_AGG(q.open ORDER BY q.trade_date))[1] AS open,
        MAX(q.high) AS high,
        MIN(q.low) AS low,
        (ARRAY_AGG(q.close ORDER BY q.trade_date DESC))[1] AS close,
        SUM(q.volume) AS volume,
        SUM(q.amount) AS amount,
        'qfq' AS adjust_type,
        (%s::date + TIME '15:00:00')::timestamp AT TIME ZONE 'Asia/Shanghai' AS trade_datetime,
        0 AS pre_close,
        0 AS ah_vol,
        0 AS ah_amount,
        %s AS market
    FROM stock_quotes q
    WHERE q.cycle = '1d'
      AND q.market = %s
      AND q.trade_date >= %s
      AND q.trade_date <= %s
      AND q.open IS NOT NULL
      AND q.close IS NOT NULL
    GROUP BY q.code
    ON CONFLICT (code, cycle, trade_date, adjust_type) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        pre_close = 0,
        trade_datetime = EXCLUDED.trade_datetime,
        ah_vol = EXCLUDED.ah_vol,
        ah_amount = EXCLUDED.ah_amount,
        market = EXCLUDED.market
"""

# 先删后插：删除桶自然日跨度内该市场的旧周期行（含旧版按 A 股日历打标的错位行）
OVERSEAS_DELETE_SQL = """
    DELETE FROM stock_quotes
    WHERE cycle = %s AND market = %s
      AND trade_date >= %s AND trade_date <= %s
"""


def get_db_conn():
    """获取数据库连接"""
    import psycopg2
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=os.getenv('PG_PORT', '5432'),
        database=os.getenv('PG_DATABASE', 'quant_trading'),
        user=os.getenv('PG_USER', 'quant_user'),
        password=os.getenv('PG_PASSWORD'),
    )


# ===================== 沪深分支（逻辑沿用旧版，仅加 market 过滤） =====================

def is_last_trade_day_of_week(conn, target_date: date) -> bool:
    """
    基于 pretrade_date 判断 target_date 是否为该交易周的最后一个交易日。
    使用 trade_week_id(连续交易日之间无 gap 则同周) 判断。
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH trade_weeks AS (
                SELECT cal_date,
                    SUM(CASE WHEN pretrade_date != cal_date - 1 THEN 1 ELSE 0 END)
                        OVER (ORDER BY cal_date) AS week_id
                FROM trade_calendar
                WHERE is_open = 1
            )
            SELECT MAX(cal_date) FROM trade_weeks
            WHERE week_id = (SELECT week_id FROM trade_weeks WHERE cal_date = %s)
        """, (target_date,))
        max_date = cur.fetchone()[0]
        return max_date == target_date


def is_last_trade_day_of_month(conn, target_date: date) -> bool:
    """判断 target_date 是否为该月的最后一个交易日"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT MAX(cal_date) FROM trade_calendar
            WHERE is_open = 1
              AND DATE_TRUNC('month', cal_date) = DATE_TRUNC('month', %s::date)
        """, (target_date,))
        max_date = cur.fetchone()[0]
        return max_date == target_date


def get_period_range(conn, target_date: date, cycle: str) -> tuple:
    """
    获取 target_date 所在周期的交易日范围 (start_date, end_date)
    cycle: '1w' 或 '1m'
    """
    with conn.cursor() as cur:
        if cycle == '1w':
            cur.execute("""
                WITH trade_weeks AS (
                    SELECT cal_date,
                        SUM(CASE WHEN pretrade_date != cal_date - 1 THEN 1 ELSE 0 END)
                            OVER (ORDER BY cal_date) AS week_id
                    FROM trade_calendar
                    WHERE is_open = 1
                )
                SELECT MIN(cal_date), MAX(cal_date) FROM trade_weeks
                WHERE week_id = (SELECT week_id FROM trade_weeks WHERE cal_date = %s)
            """, (target_date,))
        else:  # '1m'
            cur.execute("""
                SELECT MIN(cal_date), MAX(cal_date) FROM trade_calendar
                WHERE is_open = 1
                  AND DATE_TRUNC('month', cal_date) = DATE_TRUNC('month', %s::date)
            """, (target_date,))
        start, end = cur.fetchone()
        return start, end


def check_should_run(conn, target_date: date, cycle: str) -> tuple:
    """
    检查是否应该执行计算（沪深口径）。
    返回 (should_run: bool, reason: str)
    """
    with conn.cursor() as cur:
        # 1. 检查 target_date 是否为交易日
        cur.execute("SELECT is_open FROM trade_calendar WHERE cal_date = %s", (target_date,))
        row = cur.fetchone()
        if not row or row[0] != 1:
            return False, f"{target_date} 不是交易日，跳过"

    # 2. 检查是否为该周期最后一个交易日
    if cycle == '1w':
        if not is_last_trade_day_of_week(conn, target_date):
            return False, f"{target_date} 不是该周最后一个交易日，跳过"
    else:  # '1m'
        if not is_last_trade_day_of_month(conn, target_date):
            return False, f"{target_date} 不是该月最后一个交易日，跳过"

    # 3. 检查日线数据是否已到位
    with conn.cursor() as cur:
        # 只统计沪深自身（旧版未带 market 过滤，港/美股会混入分子导致比例失真）
        cur.execute("""
            SELECT COUNT(DISTINCT code) FROM stock_quotes
            WHERE cycle = '1d' AND market = 'cn' AND trade_date = %s
        """, (target_date,))
        daily_count = cur.fetchone()[0] or 0

        cur.execute("""
            SELECT COUNT(*) FROM stock_basic
            WHERE delist_date IS NULL
              AND code NOT LIKE '8%%'
              AND code NOT LIKE '920%%'
              AND code NOT LIKE '43%%'
        """)
        total_stocks = cur.fetchone()[0] or 0

    if total_stocks > 0 and daily_count / total_stocks < 0.5:
        return False, f"日线数据覆盖不足 ({daily_count}/{total_stocks})，跳过"

    return True, "条件满足，准备计算"


def compute_aggregation(conn, target_date: date, cycle: str) -> int:
    """
    从日线聚合计算沪深周线/月线 K 线（含 index）。
    返回写入的行数。
    """
    period_start, period_end = get_period_range(conn, target_date, cycle)
    logger.info(f"聚合周期: {period_start} ~ {period_end} ({cycle})")

    with conn.cursor() as cur:
        cur.execute(CN_AGG_SQL.format(cycle=cycle),
                    (target_date, target_date, period_start, period_end))
        affected = cur.rowcount
        conn.commit()
        logger.info(f"✅ {cycle} 聚合完成: 写入 {affected} 条记录 ({target_date})")
        return affected


def run_cn(conn, cycle: str, args) -> Dict[str, Any]:
    """沪深分支（含 index）：完整保留旧版行为"""
    cycle_label = '周线' if cycle == '1w' else '月线'

    if args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(trade_date) FROM stock_quotes
                WHERE cycle = '1d' AND market = 'cn'
            """)
            latest = cur.fetchone()[0]
            if not latest:
                logger.error("沪深日线数据表为空，无法计算")
                sys.exit(1)
            target_date = latest

    logger.info(f"=== {cycle_label}聚合计算（沪深）===")
    logger.info(f"目标日期: {target_date}")

    if not args.force:
        should_run, reason = check_should_run(conn, target_date, cycle)
        if not should_run:
            logger.info(reason)
            return {'rows_affected': 0, 'skipped_reason': reason, 'date': str(target_date)}
        logger.info(reason)
    else:
        logger.info("强制模式: 跳过日期检查")

    rows = compute_aggregation(conn, target_date, cycle)
    return {'rows_affected': rows, 'date': str(target_date)}


# ===================== 港/美股分支（数据源日历驱动） =====================

def _overseas_calendar(market: str, start: date, end: date) -> Optional[Set[date]]:
    """该市场真实交易日集合（数据源驱动：HSI / .IXIC，含降级）。

    失败返回 None —— 调用方须跳过本轮，绝不用工作日/A 股日历猜测（与 import_{hk,us}_daily 口径一致）。
    """
    from collector.datasource.akshare import AkShareDataSource

    src = AkShareDataSource(market=market)
    fetch = src.download_hk_trade_dates if market == 'hk' else src.download_us_trade_dates
    return fetch(start=start.isoformat(), end=end.isoformat())


def _bucket_key(cycle: str, d: date) -> date:
    """周期桶标识：1w → 该 ISO 周的周一；1m → 该自然月 1 号"""
    if cycle == '1w':
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def _bucket_span(cycle: str, key: date) -> Tuple[date, date]:
    """周期桶的自然日跨度（左闭右闭）：1w → 周一~周日；1m → 1 号~月末"""
    if cycle == '1w':
        return key, key + timedelta(days=6)
    return key, (key + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _bucket_settleable(cycle: str, key: date, as_of: date) -> bool:
    """该周期桶是否已可结算。

    港/美股周六、周日休市（真实交易日判定仍完全取自数据源日历，此判据只决定「何时可结算」）：
    - 1w：该 ISO 周的周六已到 → 本周不可能再产生交易日
    - 1m：自然月末已到
    """
    if cycle == '1w':
        return key + timedelta(days=5) <= as_of
    return _bucket_span(cycle, key)[1] <= as_of


def _bucket_keys(cycle: str, start: date, end: date) -> List[date]:
    """列举 [start, end] 覆盖到的全部周期桶（升序）"""
    keys: List[date] = []
    key = _bucket_key(cycle, start)
    last = _bucket_key(cycle, end)
    step = timedelta(days=7) if cycle == '1w' else None
    while key <= last:
        keys.append(key)
        if step is not None:
            key = key + step
        else:
            key = (key + timedelta(days=32)).replace(day=1)
    return keys


def _load_market_daily_dates(conn, market: str, start: date, end: date) -> Set[date]:
    """该市场已落库的日线交易日集合（区间内）"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT trade_date FROM stock_quotes
            WHERE cycle = '1d' AND market = %s
              AND trade_date >= %s AND trade_date <= %s
        """, (market, start, end))
        return {r[0] for r in cur.fetchall()}


def _group_by_bucket(cycle: str, days: Set[date]) -> Dict[date, Set[date]]:
    grouped: Dict[date, Set[date]] = {}
    for d in days:
        grouped.setdefault(_bucket_key(cycle, d), set()).add(d)
    return grouped


def compute_overseas_bucket(conn, market: str, cycle: str, start: date, end: date,
                            label: date) -> int:
    """先删后插单个周期桶：删除该市场桶内旧行，再按 [start, end] 聚合写入 label 日。"""
    with conn.cursor() as cur:
        span_start, span_end = _bucket_span(cycle, _bucket_key(cycle, label))
        cur.execute(OVERSEAS_DELETE_SQL, (cycle, market, span_start, span_end))
        deleted = cur.rowcount

        cur.execute(OVERSEAS_AGG_SQL, (cycle, label, label, market, market, start, end))
        affected = cur.rowcount
        conn.commit()
    logger.info(
        f"  ✅ {market} {cycle} {start} ~ {end} → 打标 {label}: "
        f"写入 {affected} 条（先删 {deleted} 条）"
    )
    return affected


def run_overseas(conn, market: str, cycle: str, args) -> Dict[str, int]:
    """港/美股分支：按该市场数据源日历划分周期桶并聚合。"""
    cycle_label = '周线' if cycle == '1w' else '月线'
    as_of = datetime.strptime(args.date, '%Y-%m-%d').date() if args.date else date.today()

    if args.rebuild and args.rebuild_from:
        rebuild_start = datetime.strptime(args.rebuild_from, '%Y-%m-%d').date()
        rebuild_end = (datetime.strptime(args.rebuild_to, '%Y-%m-%d').date()
                       if args.rebuild_to else as_of)
        keys = _bucket_keys(cycle, rebuild_start, rebuild_end)
        window_start = _bucket_span(cycle, keys[0])[0]
        window_end = _bucket_span(cycle, keys[-1])[1]
    else:
        lookback = args.lookback_periods or DEFAULT_LOOKBACK[cycle]
        last_key = _bucket_key(cycle, as_of)
        first_key = last_key
        for _ in range(lookback - 1):
            if cycle == '1w':
                first_key = first_key - timedelta(days=7)
            else:
                first_key = (first_key - timedelta(days=1)).replace(day=1)
        keys = _bucket_keys(cycle, first_key, last_key)
        window_start = _bucket_span(cycle, first_key)[0]
        window_end = _bucket_span(cycle, last_key)[1]

    logger.info(f"=== {cycle_label}聚合计算（{market}）===")
    logger.info(f"周期桶: {len(keys)} 个（{keys[0]} ~ {keys[-1]}），回看窗口 {window_start} ~ {window_end}")

    cal = _overseas_calendar(market, window_start, window_end)
    if cal is None:
        logger.warning(f"⚠️ {market} 数据源交易日历不可用，本轮跳过（不猜测、不写入）")
        return {'rows_affected': 0, 'buckets_written': 0, 'buckets_skipped': len(keys)}

    have = _load_market_daily_dates(conn, market, window_start, window_end)
    cal_by_bucket = _group_by_bucket(cycle, cal)
    have_by_bucket = _group_by_bucket(cycle, have)

    rows_total = 0
    written = 0
    skipped = 0
    for key in keys:
        if not _bucket_settleable(cycle, key, as_of):
            continue
        cal_days = cal_by_bucket.get(key, set())
        have_days = have_by_bucket.get(key, set())
        if not cal_days and not have_days:
            continue  # 该周期该市场全休
        # 交易日 = 日历 ∩ 桶 ∪ 库中已有（日历偶发缺日时以库为准，避免漏聚合）
        days = sorted(cal_days | have_days)
        missing = sorted(cal_days - have_days)
        if missing:
            skipped += 1
            logger.info(
                f"  ⏭️ {market} {cycle} {key} 周期交易日未齐备（缺 "
                f"{', '.join(str(d) for d in missing)}），跳过"
            )
            continue
        rows_total += compute_overseas_bucket(conn, market, cycle, days[0], days[-1], days[-1])
        written += 1

    logger.info(
        f"✅ {market} {cycle_label}聚合完成：写入 {written} 个周期 / {rows_total} 条记录，"
        f"跳过 {skipped} 个未齐备周期"
    )
    return {'rows_affected': rows_total, 'buckets_written': written, 'buckets_skipped': skipped}


# ===================== 日志清理（随月线聚合每月执行一次） =====================

def cleanup_expired_logs(retention_days: int = 60) -> None:
    """清理超过保留天数的日志文件（随月K线聚合每月执行一次）。

    Args:
        retention_days: 日志保留天数，默认 60 天
    """
    log_root = os.path.join(BASE_DIR, 'logs')
    if not os.path.isdir(log_root):
        logger.warning(f"日志目录不存在，跳过清理: {log_root}")
        return

    now = datetime.now().timestamp()
    cutoff = retention_days * 86400
    removed = 0
    for root, _, files in os.walk(log_root):
        for name in files:
            if not (name.endswith('.log') or name.endswith('.gz')
                    or name.endswith('.err.log') or name.endswith('.stdout.log')
                    or name.endswith('.stderr.log')):
                continue
            path = os.path.join(root, name)
            try:
                if now - os.path.getmtime(path) > cutoff:
                    os.remove(path)
                    removed += 1
                    logger.info(f"清理过期日志: {os.path.relpath(path, log_root)}")
            except OSError as e:
                logger.warning(f"清理日志失败 {path}: {e}")

    if removed:
        logger.info(f"✅ 日志清理完成，共删除 {removed} 个过期文件（> {retention_days} 天）")
    else:
        logger.info(f"日志清理：无超过 {retention_days} 天的日志文件")


def main():
    parser = argparse.ArgumentParser(description='周线/月线 K 线聚合计算')
    parser.add_argument('--cycle', required=True, choices=['1w', '1m'],
                        help='计算周期: 1w=周线, 1m=月线')
    parser.add_argument('--market', default='cn',
                        help='市场: cn(默认,含index) / hk / us，可逗号组合如 hk,us')
    parser.add_argument('--date', type=str, default=None,
                        help='沪深=目标日期；港美股=「视作该日运行」(默认今天)')
    parser.add_argument('--force', action='store_true',
                        help='沪深强制计算，跳过日期检查')
    parser.add_argument('--lookback-periods', type=int, default=None,
                        help='港美股正常运行回看的周期桶数（默认 1w=4, 1m=3）')
    parser.add_argument('--rebuild', action='store_true',
                        help='港美股历史回填模式：遍历 --from/--to 区间内全部周期桶')
    parser.add_argument('--from', dest='rebuild_from', type=str, default=None,
                        help='回填起始日期 YYYY-MM-DD（配合 --rebuild）')
    parser.add_argument('--to', dest='rebuild_to', type=str, default=None,
                        help='回填结束日期 YYYY-MM-DD（配合 --rebuild，默认今天）')
    args = parser.parse_args()

    markets = [m.strip().lower() for m in args.market.split(',') if m.strip()]
    invalid = [m for m in markets if m not in OVERSEAS_MARKETS and m != 'cn']
    if invalid:
        parser.error(f"不支持的 market: {invalid}（可选 cn / hk / us，可逗号组合）")
    if args.rebuild and not args.rebuild_from:
        parser.error('--rebuild 需配合 --from YYYY-MM-DD')
    if args.rebuild and 'cn' in markets:
        parser.error('--rebuild 仅支持港/美股（沪深历史不做重建）')

    conn = get_db_conn()
    conn.autocommit = False

    try:
        total_rows = 0
        results = {}
        for market in markets:
            if market == 'cn':
                r = run_cn(conn, args.cycle, args)
            else:
                r = run_overseas(conn, market, args.cycle, args)
            total_rows += r['rows_affected']
            results[market] = r

        extra = {'cycle': args.cycle, 'markets': results}
        print(f"TASK_RESULT:{json.dumps({'rows_affected': total_rows, 'extra_metrics': extra}, ensure_ascii=False)}")

        # 月线聚合完成后顺带清理过期日志（每月一次）
        if args.cycle == '1m':
            cleanup_expired_logs()

    except Exception as e:
        conn.rollback()
        cycle_label = '周线' if args.cycle == '1w' else '月线'
        logger.error(f"❌ {cycle_label}聚合失败: {e}", exc_info=True)
        print(f"TASK_RESULT:{json.dumps({'rows_affected': 0, 'extra_metrics': {'error': str(e)}}, ensure_ascii=False)}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()