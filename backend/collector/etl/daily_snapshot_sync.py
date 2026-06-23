#!/usr/bin/env python3
"""
daily_snapshot_sync.py - 每日快照宽表增量同步脚本

用于将 stock_quotes、stock_basic、stock_indicators 三表数据合并到
stock_daily_snapshot 宽表，支持首次全量同步和每日增量同步。

可通过 Airflow/Cron 调度执行。

【必需的数据库索引】
CREATE INDEX idx_quotes_cycle_date_code ON stock_quotes(cycle, trade_date DESC, code);
CREATE INDEX idx_indicators_code_cycle_date ON stock_indicators(code, cycle, trade_date DESC);
CREATE UNIQUE INDEX idx_snapshot_code_date ON stock_daily_snapshot(code, trade_date);
CREATE INDEX idx_basic_code ON stock_basic(code);
CREATE INDEX idx_daily_basic_code_date ON stock_daily_basic(code, trade_date);

【依赖说明】
- stock_indicators 表需预先计算并存储 MA5/MA10/MA20/V_MA5/BOLL 等指标。
- 本脚本从该表直接读取这些指标，避免重复计算。
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from collector.db.models import StockDailySnapshot, Base

logger = logging.getLogger(__name__)

# 2026-06-22 修复：涨跌停阈值使用精确值（考虑浮点误差，使用略低于理论阈值）
# 理论阈值：主板10%，创业板/科创板20%，北交所30%
# 实际判断：>=9.95/>=19.95/>=29.95，避免浮点误差导致漏判
LIMIT_THRESHOLDS = {
    'main_board': 9.95,  # 主板涨停阈值（理论10%）
    'gem': 19.95,        # 创业板/科创板涨停阈值（理论20%）
    'beijing': 29.95,    # 北交所涨停阈值（理论30%）
}


def sync_daily_snapshot(session: Session, target_date: str) -> int:
    """同步指定日期的宽表数据，返回影响行数"""
    try:
        logger.info(f"🔄 开始同步 {target_date} 的宽表数据...")

        upsert_sql = text("""
            INSERT INTO stock_daily_snapshot (
                code, stock_name, listed_board, industry, sub_industry, area,
                trade_date, open, high, low, close, pre_close, volume, amount, adjust_type,
                change, change_pct, pe, pe_ttm, pb, market_cap, circ_mv, turnover_rate, volume_ratio,
                dv_ratio, dv_ttm, ps, ps_ttm, float_share,
                ma5, ma10, ma20, v_ma5, rsi_6, macd, dif, dea, rsi_12, rsi_24,
                boll_upper, boll_mid, boll_lower,
                break_high_20, break_high_60, consec_up_days, vol_ratio_5,
                is_st, is_new, limit_up, limit_down
            )
            WITH
            qdata AS (
                SELECT code, trade_date, open, high, low, close, pre_close, volume, amount, adjust_type
                FROM stock_quotes
                WHERE cycle = '1d' AND trade_date = :target_date
            ),
            win AS (
                SELECT code, trade_date, close, high, volume
                FROM stock_quotes
                WHERE cycle = '1d'
                  AND trade_date <= :target_date
                  AND trade_date >= CAST(:target_date AS DATE) - INTERVAL '70 days'
                  AND code IN (SELECT code FROM qdata)
            ),
            ranked AS (
                SELECT code, trade_date, close, high, volume,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                FROM win
            ),
            stats AS (
                SELECT code,
                       MAX(high) FILTER (WHERE rn BETWEEN 2 AND 21) AS high_20,
                       MAX(high) FILTER (WHERE rn BETWEEN 2 AND 61) AS high_60,
                       AVG(volume) FILTER (WHERE rn BETWEEN 2 AND 6) AS vol_5_avg
                FROM ranked
                GROUP BY code
            ),
            -- 【修复】先计算LEAD，再计算SUM，避免窗口函数嵌套
            lead_calc AS (
                SELECT code, close, rn,
                       LEAD(close) OVER (PARTITION BY code ORDER BY rn) AS prev_close
                FROM ranked
            ),
            consec AS (
                SELECT code, COUNT(*) AS consec_up_days
                FROM (
                    SELECT code,
                           SUM(CASE WHEN close > prev_close THEN 0 ELSE 1 END)
                               OVER (PARTITION BY code ORDER BY rn) AS grp
                    FROM lead_calc
                ) flagged
                WHERE grp = 0
                GROUP BY code
            )
            SELECT
                q.code,
                COALESCE(b.name, '') AS stock_name,
                CASE
                    WHEN q.code LIKE '60%' THEN '上海主板'
                    WHEN q.code LIKE '000%' OR q.code LIKE '001%' OR q.code LIKE '002%' OR q.code LIKE '003%' THEN '深圳主板'
                    WHEN q.code LIKE '300%' OR q.code LIKE '301%' OR q.code LIKE '302%' THEN '创业板'
                    WHEN q.code LIKE '688%' OR q.code LIKE '689%' THEN '科创板'
                    WHEN q.code LIKE '92%' OR q.code LIKE '8%' OR q.code LIKE '43%' THEN '北交所'
                    ELSE '其他'
                END AS listed_board,
                COALESCE(b.industry, '') AS industry,
                COALESCE(b.industry, '') AS sub_industry,
                COALESCE(b.area, '') AS area,
                q.trade_date,
                q.open, q.high, q.low, q.close, q.pre_close, q.volume, q.amount, q.adjust_type,
                ROUND(q.close - q.pre_close, 2) AS change,
                ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) AS change_pct,
                db.pe, db.pe_ttm, db.pb,
                db.total_mv AS market_cap,
                db.circ_mv, db.turnover_rate, db.volume_ratio,
                db.dv_ratio, db.dv_ttm, db.ps, db.ps_ttm, db.float_share,
                ROUND(i.ma5::numeric, 2) AS ma5,
                ROUND(i.ma10::numeric, 2) AS ma10,
                ROUND(i.ma20::numeric, 2) AS ma20,
                s.vol_5_avg::bigint AS v_ma5,
                ROUND(i.rsi6::numeric, 2) AS rsi_6,
                ROUND(i.macd::numeric, 4) AS macd,
                ROUND(i.dif::numeric, 4) AS dif,
                ROUND(i.dea::numeric, 4) AS dea,
                ROUND(i.rsi12::numeric, 2) AS rsi_12,
                ROUND(i.rsi24::numeric, 2) AS rsi_24,
                ROUND(i.boll_upper::numeric, 2) AS boll_upper,
                ROUND(i.boll_mid::numeric, 2) AS boll_mid,
                ROUND(i.boll_lower::numeric, 2) AS boll_lower,
                (s.high_20 IS NOT NULL AND q.high > s.high_20) AS break_high_20,
                (s.high_60 IS NOT NULL AND q.high > s.high_60) AS break_high_60,
                COALESCE(c.consec_up_days, 0) AS consec_up_days,
                CASE WHEN s.vol_5_avg IS NOT NULL AND s.vol_5_avg > 0
                     THEN ROUND((q.volume / s.vol_5_avg)::numeric, 2) ELSE NULL END AS vol_ratio_5,
                NULL::boolean AS is_st,
                CASE WHEN b.list_date IS NOT NULL 
                     AND b.list_date >= CAST(:target_date AS DATE) - INTERVAL '365 days' 
                     THEN TRUE ELSE FALSE END AS is_new,
                -- 新股豁免：上市后前5个自然日无涨跌停限制（修复类型错误：使用 > 5）
                CASE 
                  WHEN q.pre_close IS NOT NULL AND q.pre_close > 0
                    AND (b.list_date IS NULL 
                         OR CAST(:target_date AS DATE) - b.list_date > 5) THEN
                    CASE
                      WHEN q.code LIKE '300%' OR q.code LIKE '301%' OR q.code LIKE '302%' 
                           OR q.code LIKE '688%' OR q.code LIKE '689%' THEN
                        (q.close - q.pre_close) / q.pre_close * 100 >= :gem_limit
                      WHEN q.code LIKE '92%' OR q.code LIKE '8%' OR q.code LIKE '43%' THEN
                        (q.close - q.pre_close) / q.pre_close * 100 >= :bj_limit
                      ELSE
                        (q.close - q.pre_close) / q.pre_close * 100 >= :main_limit
                    END
                  ELSE FALSE
                END AS limit_up,
                CASE 
                  WHEN q.pre_close IS NOT NULL AND q.pre_close > 0
                    AND (b.list_date IS NULL 
                         OR CAST(:target_date AS DATE) - b.list_date > 5) THEN
                    CASE
                      WHEN q.code LIKE '300%' OR q.code LIKE '301%' OR q.code LIKE '302%' 
                           OR q.code LIKE '688%' OR q.code LIKE '689%' THEN
                        (q.close - q.pre_close) / q.pre_close * 100 <= -:gem_limit
                      WHEN q.code LIKE '92%' OR q.code LIKE '8%' OR q.code LIKE '43%' THEN
                        (q.close - q.pre_close) / q.pre_close * 100 <= -:bj_limit
                      ELSE
                        (q.close - q.pre_close) / q.pre_close * 100 <= -:main_limit
                    END
                  ELSE FALSE
                END AS limit_down
            FROM qdata q
            LEFT JOIN stock_basic b ON q.code = b.code
            LEFT JOIN stats s ON q.code = s.code
            LEFT JOIN consec c ON q.code = c.code
            LEFT JOIN stock_indicators i ON q.code = i.code AND i.cycle = '1d'
                AND i.trade_date = :target_date
            LEFT JOIN stock_daily_basic db ON q.code = db.code AND db.trade_date = :target_date
            ON CONFLICT (code, trade_date) DO UPDATE SET
                stock_name = EXCLUDED.stock_name,
                listed_board = EXCLUDED.listed_board,
                industry = EXCLUDED.industry,
                sub_industry = EXCLUDED.sub_industry,
                area = EXCLUDED.area,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                pre_close = EXCLUDED.pre_close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                adjust_type = EXCLUDED.adjust_type,
                change = EXCLUDED.change,
                change_pct = EXCLUDED.change_pct,
                pe = EXCLUDED.pe,
                pe_ttm = EXCLUDED.pe_ttm,
                pb = EXCLUDED.pb,
                market_cap = EXCLUDED.market_cap,
                circ_mv = EXCLUDED.circ_mv,
                turnover_rate = EXCLUDED.turnover_rate,
                volume_ratio = EXCLUDED.volume_ratio,
                dv_ratio = EXCLUDED.dv_ratio,
                dv_ttm = EXCLUDED.dv_ttm,
                ps = EXCLUDED.ps,
                ps_ttm = EXCLUDED.ps_ttm,
                float_share = EXCLUDED.float_share,
                ma5 = EXCLUDED.ma5,
                ma10 = EXCLUDED.ma10,
                ma20 = EXCLUDED.ma20,
                v_ma5 = EXCLUDED.v_ma5,
                rsi_6 = EXCLUDED.rsi_6,
                macd = EXCLUDED.macd,
                dif = EXCLUDED.dif,
                dea = EXCLUDED.dea,
                rsi_12 = EXCLUDED.rsi_12,
                rsi_24 = EXCLUDED.rsi_24,
                boll_upper = EXCLUDED.boll_upper,
                boll_mid = EXCLUDED.boll_mid,
                boll_lower = EXCLUDED.boll_lower,
                break_high_20 = EXCLUDED.break_high_20,
                break_high_60 = EXCLUDED.break_high_60,
                consec_up_days = EXCLUDED.consec_up_days,
                vol_ratio_5 = EXCLUDED.vol_ratio_5,
                is_st = EXCLUDED.is_st,
                is_new = EXCLUDED.is_new,
                limit_up = EXCLUDED.limit_up,
                limit_down = EXCLUDED.limit_down,
                updated_at = CURRENT_TIMESTAMP
        """)

        params = {
            'target_date': target_date,
            'main_limit': LIMIT_THRESHOLDS['main_board'],
            'gem_limit': LIMIT_THRESHOLDS['gem'],
            'bj_limit': LIMIT_THRESHOLDS['beijing'],
        }

        session.execute(upsert_sql, params)
        result = session.execute(text("SELECT COUNT(*) FROM stock_daily_snapshot WHERE trade_date = :d"), {"d": target_date})
        row_count = result.scalar()
        logger.info(f"✅ {target_date} 基础数据同步完成，共 {row_count} 条")

        _update_tech_patterns(session, target_date)

        session.commit()
        logger.info(f"✅ {target_date} 宽表同步完成")
        return row_count

    except Exception as e:
        session.rollback()
        logger.error(f"❌ {target_date} 同步失败: {e}")
        raise


def _update_tech_patterns(session: Session, target_date: str):
    """更新技术形态 pattern（使用 ROW_NUMBER 仅取最近两日）"""
    logger = logging.getLogger(__name__)

    check_sql = text("""
        SELECT COUNT(*) FROM stock_indicators
        WHERE trade_date = :target_date AND cycle = '1d'
    """)
    cnt = session.execute(check_sql, {'target_date': target_date}).scalar()
    if cnt == 0:
        logger.warning(f"⚠️ {target_date} 无当日指标数据，跳过 pattern 更新")
        return

    all_patterns_sql = text("""
        WITH
        cur_indicators AS (
            SELECT code, macd, dea, dif, rsi6, rsi24
            FROM stock_indicators
            WHERE cycle = '1d' AND trade_date = :target_date
        ),
        prev_indicators AS (
            SELECT code, macd, dea, dif, rsi6, rsi24
            FROM (
                SELECT code, macd, dea, dif, rsi6, rsi24,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                FROM stock_indicators
                WHERE cycle = '1d' AND trade_date <= :target_date
            ) ranked
            WHERE rn = 2
        ),
        cur_quotes AS (
            SELECT code, close
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = :target_date
        ),
        -- 【已修复】使用 ROW_NUMBER 仅取第二近（前一交易日），避免全表扫描
        prev_close AS (
            SELECT code, close AS close_prev
            FROM (
                SELECT code, close,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                FROM stock_quotes
                WHERE cycle = '1d' AND trade_date <= :target_date
            ) ranked
            WHERE rn = 2
        ),
        -- 【修复】内联计算 BOLL 指标（20日中轨 ± 2倍标准差）
        boll_calc AS (
            SELECT code,
                   AVG(close) AS boll_mid,
                   STDDEV(close) AS boll_std
            FROM (
                SELECT code, close,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                FROM stock_quotes
                WHERE cycle = '1d'
                  AND trade_date <= :target_date
                  AND trade_date >= CAST(:target_date AS DATE) - INTERVAL '30 days'
            ) recent
            WHERE rn <= 20
            GROUP BY code
            HAVING COUNT(*) >= 20
        )
        UPDATE stock_daily_snapshot s
        SET
            ma_long_align = (s.ma5 IS NOT NULL AND s.ma5 > s.ma10 AND s.ma10 > s.ma20),
            ma_short_align = (s.ma5 IS NOT NULL AND s.ma5 < s.ma10 AND s.ma10 < s.ma20),
            macd_low_golden_cross = (
                ci.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND pi.macd < pi.dea AND ci.macd >= ci.dea
            ),
            macd_high_death_cross = (
                ci.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND pi.macd > pi.dea AND ci.macd <= ci.dea
            ),
            macd_bottom_divergence = (
                cq.close IS NOT NULL AND pc.close_prev IS NOT NULL
                AND ci.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND cq.close < pc.close_prev
                AND ci.macd > pi.macd
            ),
            macd_top_divergence = (
                cq.close IS NOT NULL AND pc.close_prev IS NOT NULL
                AND ci.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND cq.close > pc.close_prev
                AND ci.macd < pi.macd
            ),
            rsi_low_golden_cross = (
                ci.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND ci.rsi24 IS NOT NULL AND pi.rsi24 IS NOT NULL
                AND ci.rsi6 < 30 AND pi.rsi6 < 30
                AND pi.rsi6 <= pi.rsi24 AND ci.rsi6 > ci.rsi24
            ),
            rsi_high_death_cross = (
                ci.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND ci.rsi24 IS NOT NULL AND pi.rsi24 IS NOT NULL
                AND ci.rsi6 > 70 AND pi.rsi6 > 70
                AND pi.rsi6 >= pi.rsi24 AND ci.rsi6 < ci.rsi24
            ),
            rsi_bottom_divergence = (
                cq.close IS NOT NULL AND pc.close_prev IS NOT NULL
                AND ci.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND cq.close < pc.close_prev
                AND ci.rsi6 > pi.rsi6
            ),
            rsi_top_divergence = (
                cq.close IS NOT NULL AND pc.close_prev IS NOT NULL
                AND ci.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND cq.close > pc.close_prev
                AND ci.rsi6 < pi.rsi6
            ),
            boll_break_upper = (
                bc.boll_mid IS NOT NULL AND bc.boll_std IS NOT NULL
                AND pc.close_prev IS NOT NULL
                AND s.close > (bc.boll_mid + 2 * bc.boll_std)
                AND pc.close_prev <= (bc.boll_mid + 2 * bc.boll_std)
            ),
            boll_break_middle_up = (
                bc.boll_mid IS NOT NULL
                AND pc.close_prev IS NOT NULL
                AND s.close > bc.boll_mid AND pc.close_prev <= bc.boll_mid
            ),
            boll_break_middle_down = (
                bc.boll_mid IS NOT NULL
                AND pc.close_prev IS NOT NULL
                AND s.close < bc.boll_mid AND pc.close_prev >= bc.boll_mid
            ),
            boll_break_lower = (
                bc.boll_mid IS NOT NULL AND bc.boll_std IS NOT NULL
                AND pc.close_prev IS NOT NULL
                AND s.close < (bc.boll_mid - 2 * bc.boll_std)
                AND pc.close_prev >= (bc.boll_mid - 2 * bc.boll_std)
            )
        FROM cur_indicators ci
        LEFT JOIN prev_indicators pi ON ci.code = pi.code
        LEFT JOIN cur_quotes cq ON ci.code = cq.code
        LEFT JOIN prev_close pc ON ci.code = pc.code
        LEFT JOIN boll_calc bc ON ci.code = bc.code
        WHERE s.code = ci.code AND s.trade_date = :target_date
    """)

    result = session.execute(all_patterns_sql, {'target_date': target_date})
    logger.info(f"  ✓ 全部 pattern 更新完成，影响 {result.rowcount} 行")


def sync_date_range(
    session: Session,
    start_date: str,
    end_date: str,
    ignore_errors: bool = False
) -> int:
    """同步日期范围，返回总影响行数"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    failed_dates = []
    total_count = 0
    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        try:
            cnt = sync_daily_snapshot(session, date_str)
            if cnt is not None:
                total_count += cnt
        except Exception as e:
            if ignore_errors:
                logger.warning(f"⚠️ 跳过 {date_str}: {e}")
                failed_dates.append(date_str)
            else:
                logger.error(f"❌ 同步 {date_str} 失败，终止执行")
                raise
        current += timedelta(days=1)

    if failed_dates:
        logger.error(f"❌ 同步失败的日期（共 {len(failed_dates)} 个）：{', '.join(failed_dates)}")
    else:
        logger.info(f"✅ 日期范围 {start_date} ~ {end_date} 全部同步成功，共 {total_count} 条")
    return total_count


def get_latest_trade_date(engine) -> Optional[str]:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'"))
        row = result.fetchone()
        return row[0].strftime('%Y-%m-%d') if row[0] else None


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description='股票每日快照宽表同步脚本')
    parser.add_argument('--date', type=str, help='同步指定日期')
    parser.add_argument('--start-date', type=str, help='同步开始日期')
    parser.add_argument('--end-date', type=str, help='同步结束日期')
    parser.add_argument('--latest', action='store_true', help='同步最新交易日')
    parser.add_argument('--ignore-errors', action='store_true', help='范围同步时忽略单日错误')
    args = parser.parse_args()

    from collector.db.database import DATABASE_URL
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        count = 0
        if args.date:
            count = sync_daily_snapshot(session, args.date)
        elif args.start_date and args.end_date:
            count = sync_date_range(session, args.start_date, args.end_date, args.ignore_errors)
        elif args.latest:
            latest_date = get_latest_trade_date(engine)
            if latest_date:
                count = sync_daily_snapshot(session, latest_date)
            else:
                logger.error("❌ 未找到最新交易日期")
        else:
            parser.print_help()
        if count > 0:
            print(f'TASK_RESULT:{json.dumps({"rows_affected": count})}')
    finally:
        session.close()
        engine.dispose()


if __name__ == '__main__':
    main()