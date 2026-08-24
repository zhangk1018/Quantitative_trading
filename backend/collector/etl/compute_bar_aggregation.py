#!/usr/bin/env python3
"""
周线/月线 K 线聚合计算脚本

从日线('1d')数据聚合生成周线('1w')或月线('1m')K 线。
- 仅在交易日运行，自动判断当日是否为周/月最后一个交易日
- 支持指定日期回算历史数据
- 使用 ON CONFLICT 实现幂等写入

用法:
    # 周线计算（每周最后交易日 19:00 执行）
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1w

    # 月线计算（每月最后交易日 20:00 执行）
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1m

    # 指定日期回算
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1w --date 2026-08-07
    ./venv/bin/python backend/collector/etl/compute_bar_aggregation.py --cycle 1m --date 2026-07-31
"""
import os
import sys
import json
import argparse
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.logger import setup_logger

logger = setup_logger('bar_aggregation')

# ===================== 数据库连接 =====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))


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
    检查是否应该执行计算。
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
        cur.execute("""
            SELECT COUNT(DISTINCT code) FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = %s
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

    return True, f"条件满足，准备计算"


def compute_aggregation(conn, target_date: date, cycle: str) -> int:
    """
    从日线聚合计算周线/月线 K 线。
    返回写入的行数。
    """
    period_start, period_end = get_period_range(conn, target_date, cycle)
    logger.info(f"聚合周期: {period_start} ~ {period_end} ({cycle})")

    with conn.cursor() as cur:
        # 第1步：核心 OHLCV 聚合（不含 pre_close，避免慢速子查询）
        cur.execute(f"""
            INSERT INTO stock_quotes (code, cycle, trade_date, open, high, low, close,
                                       volume, amount, adjust_type, trade_datetime, pre_close, ah_vol, ah_amount)
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
                0 AS ah_amount
            FROM stock_quotes q
            WHERE q.cycle = '1d'
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
                ah_amount = EXCLUDED.ah_amount
        """, (target_date, target_date, period_start, period_end))

        affected = cur.rowcount
        conn.commit()
        logger.info(f"✅ {cycle} 聚合完成: 写入 {affected} 条记录 ({target_date})")
        return affected


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
    parser.add_argument('--date', type=str, default=None,
                        help='目标日期 (默认: 最新交易日)')
    parser.add_argument('--force', action='store_true',
                        help='强制计算，跳过日期检查')
    args = parser.parse_args()

    cycle = args.cycle
    cycle_label = '周线' if cycle == '1w' else '月线'

    conn = get_db_conn()
    conn.autocommit = False

    try:
        # 确定目标日期
        if args.date:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        else:
            with conn.cursor() as cur:
                # 找最新已完成的交易日（日线数据已就绪的日期）
                cur.execute("""
                    SELECT MAX(trade_date) FROM stock_quotes
                    WHERE cycle = '1d'
                """)
                latest = cur.fetchone()[0]
                if not latest:
                    logger.error("日线数据表为空，无法计算")
                    sys.exit(1)
                target_date = latest

        logger.info(f"=== {cycle_label}聚合计算 ===")
        logger.info(f"目标日期: {target_date}")

        # 检查是否应执行
        if not args.force:
            should_run, reason = check_should_run(conn, target_date, cycle)
            if not should_run:
                logger.info(reason)
                # 输出 TASK_RESULT 供 daily_job_runner 解析
                print(f"TASK_RESULT:{{\"rows_affected\":0,\"extra_metrics\":{{\"date\":\"{target_date}\",\"reason\":\"{reason}\"}}}}")
                sys.exit(0)
            logger.info(reason)
        else:
            logger.info("强制模式: 跳过日期检查")

        # 执行聚合
        affected = compute_aggregation(conn, target_date, cycle)

        # 输出 TASK_RESULT 供 daily_job_runner 解析
        print(f"TASK_RESULT:{{\"rows_affected\":{affected},\"extra_metrics\":{{\"date\":\"{target_date}\",\"cycle\":\"{cycle}\"}}}}")
        logger.info(f"✅ {cycle_label}聚合完成，共 {affected} 条记录")

        # 月线聚合完成后顺带清理过期日志（每月一次）
        if cycle == '1m':
            cleanup_expired_logs()

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ {cycle_label}聚合失败: {e}", exc_info=True)
        print(f"TASK_RESULT:{{\"rows_affected\":0,\"extra_metrics\":{{\"error\":\"{e}\"}}}}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()