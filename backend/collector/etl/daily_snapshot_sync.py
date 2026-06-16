#!/usr/bin/env python3
"""
daily_snapshot_sync.py - 每日快照宽表增量同步脚本

用于将 stock_quotes、stock_basic、stock_indicators 三表数据合并到
stock_daily_snapshot 宽表，支持首次全量同步和每日增量同步。

可通过 Airflow/Cron 调度执行。
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from collector.db.models import StockDailySnapshot, Base

logger = logging.getLogger(__name__)


def get_db_engine():
    """获取数据库引擎"""
    from collector.db.database import DATABASE_URL
    return create_engine(DATABASE_URL)


def sync_daily_snapshot(target_date: str, batch_size: int = 10000):
    """
    同步指定日期的宽表数据
    
    Args:
        target_date: 目标日期（格式：YYYY-MM-DD）
        batch_size: 批量处理大小
    """
    engine = get_db_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        logger.info(f"🔄 开始同步 {target_date} 的宽表数据...")
        
        # 1. 使用 SQL 计算并插入/更新（利用数据库计算能力）
        # PostgreSQL UPSERT 语法：INSERT ... ON CONFLICT DO UPDATE
        # 2026-06-10: 扩展 SELECT 增加 boll/break_high/consec_up_days/vol_ratio_5/v_ma5/area
        # 2026-06-16: 新增 14 个技术指标 pattern 列（ma/macd/boll/rsi 筛选 pattern）
        upsert_sql = text("""
            INSERT INTO stock_daily_snapshot (
                code, stock_name, listed_board, industry, sub_industry, area,
                trade_date, open, high, low, close, pre_close, volume, amount, adjust_type,
                change, change_pct, pe, pe_ttm, pb, market_cap, circ_mv, turnover_rate, volume_ratio,
                dv_ratio, dv_ttm, ps, ps_ttm, float_share,
                ma5, ma10, ma20, v_ma5, rsi_6, macd,
                boll_upper, boll_mid, boll_lower,
                break_high_20, break_high_60, consec_up_days, vol_ratio_5,
                is_st, is_new, limit_up, limit_down
            )
            WITH
            qdata AS (
                SELECT code, trade_date, open, high, low, close, pre_close, volume, amount, adjust_type
                FROM stock_quotes
                WHERE cycle = '1d' AND trade_date = :target_date
                  AND code NOT LIKE '92%'
                  AND code NOT LIKE '8%'
                  AND code NOT LIKE '43%'
            ),
            -- 拉取 70 天窗口
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
                       AVG(close) FILTER (WHERE rn BETWEEN 6 AND 10)  AS ma5,
                       AVG(close) FILTER (WHERE rn BETWEEN 11 AND 20) AS ma10,
                       AVG(close) FILTER (WHERE rn BETWEEN 21 AND 40) AS ma20,
                       AVG(volume) FILTER (WHERE rn BETWEEN 2 AND 6)  AS v_ma5,
                       AVG(close) FILTER (WHERE rn BETWEEN 2 AND 21)  AS boll_mid,
                       STDDEV_SAMP(close) FILTER (WHERE rn BETWEEN 2 AND 21) AS boll_std,
                       AVG(close) FILTER (WHERE rn BETWEEN 2 AND 21) + 2 * STDDEV_SAMP(close) FILTER (WHERE rn BETWEEN 2 AND 21) AS boll_upper,
                       AVG(close) FILTER (WHERE rn BETWEEN 2 AND 21) - 2 * STDDEV_SAMP(close) FILTER (WHERE rn BETWEEN 2 AND 21) AS boll_lower,
                       MAX(high)   FILTER (WHERE rn BETWEEN 21 AND 40) AS high_20,
                       MAX(high)   FILTER (WHERE rn BETWEEN 2 AND 61)  AS high_60,
                       AVG(volume) FILTER (WHERE rn BETWEEN 2 AND 6)  AS vol_5_avg
                FROM ranked
                GROUP BY code
            ),
            consec AS (
                SELECT a.code, COUNT(*) AS consec_up_days
                FROM ranked a
                JOIN ranked b ON a.code = b.code AND b.rn = a.rn - 1
                WHERE a.high > b.high
                GROUP BY a.code
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
                ROUND(s.ma5::numeric, 2) AS ma5,
                ROUND(s.ma10::numeric, 2) AS ma10,
                ROUND(s.ma20::numeric, 2) AS ma20,
                s.v_ma5::bigint AS v_ma5,
                ROUND(i.rsi6::numeric, 2) AS rsi_6,
                ROUND(i.macd::numeric, 4) AS macd,
                ROUND((s.boll_mid + 2 * COALESCE(s.boll_std, 0))::numeric, 2) AS boll_upper,
                ROUND(s.boll_mid::numeric, 2) AS boll_mid,
                ROUND((s.boll_mid - 2 * COALESCE(s.boll_std, 0))::numeric, 2) AS boll_lower,
                (s.boll_mid IS NOT NULL AND q.high > s.high_20) AS break_high_20,
                (s.high_60 IS NOT NULL AND q.high > s.high_60) AS break_high_60,
                COALESCE(c.consec_up_days, 0) AS consec_up_days,
                CASE WHEN s.vol_5_avg IS NOT NULL AND s.vol_5_avg > 0
                     THEN ROUND((q.volume / s.vol_5_avg)::numeric, 2) ELSE NULL END AS vol_ratio_5,
                FALSE, FALSE, FALSE, FALSE
            FROM qdata q
            LEFT JOIN stock_basic b ON q.code = b.code
            LEFT JOIN stats s ON q.code = s.code
            LEFT JOIN consec c ON q.code = c.code
            LEFT JOIN stock_indicators i ON q.code = i.code AND i.cycle = '1d'
                AND i.trade_date = :target_date
            LEFT JOIN LATERAL (
                SELECT pe, pe_ttm, pb, total_mv, circ_mv, turnover_rate, volume_ratio,
                       dv_ratio, dv_ttm, ps, ps_ttm, float_share
                FROM stock_daily_basic db2
                WHERE SPLIT_PART(db2.code, '.', 2) = q.code AND db2.trade_date <= q.trade_date
                ORDER BY db2.trade_date DESC LIMIT 1
            ) db ON TRUE
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
                boll_upper = EXCLUDED.boll_upper,
                boll_mid = EXCLUDED.boll_mid,
                boll_lower = EXCLUDED.boll_lower,
                break_high_20 = EXCLUDED.break_high_20,
                break_high_60 = EXCLUDED.break_high_60,
                consec_up_days = EXCLUDED.consec_up_days,
                vol_ratio_5 = EXCLUDED.vol_ratio_5,
                updated_at = CURRENT_TIMESTAMP
        """)

        result = session.execute(upsert_sql, {'target_date': target_date})
        session.commit()

        logger.info(f"✅ {target_date} 基础数据同步完成，影响 {result.rowcount} 条记录")

        # 独立计算 14 个技术指标 pattern（避免主查询过于复杂）
        _update_tech_patterns(session, target_date)
        
        logger.info(f"✅ {target_date} 宽表同步完成")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ {target_date} 同步失败: {e}")
        raise
    finally:
        session.close()

def _update_tech_patterns(session, target_date: str):
    """
    独立计算 14 个技术指标 pattern（分批次 UPDATE，降低单次查询复杂度）
    
    2026-06-16 修复版：
    - 增加数据存在性检查，避免空跑
    - 放宽 MACD/RSI 金叉死叉条件（不再限制 dif 正负）
    - 增加底背离/顶背离计算（基于股价与指标低点/高点的比较）
    - 使用 LATERAL JOIN 优化前一日数据获取，避免子查询重复执行
    - 输出每个 pattern 更新的影响行数
    """
    logger = logging.getLogger(__name__)
    
    # 1. 检查 stock_indicators 表中是否有 target_date 或之前的数据
    #    修复：indicators 可能滞后于 snapshot（如周末/节假日不更新指标）
    check_sql = text("""
        SELECT COUNT(*) FROM stock_indicators
        WHERE trade_date <= :target_date AND cycle = '1d'
    """)
    cnt = session.execute(check_sql, {'target_date': target_date}).scalar()
    if cnt == 0:
        logger.warning(f"⚠️ {target_date} 及之前无指标数据 (stock_indicators)，跳过 pattern 更新")
        session.commit()
        return

    # 2. MA pattern（基于已计算的 ma5/ma10/ma20）
    ma_sql = text("""
        UPDATE stock_daily_snapshot
        SET ma_long_align = (ma5 IS NOT NULL AND ma5 > ma10 AND ma10 > ma20),
            ma_short_align = (ma5 IS NOT NULL AND ma5 < ma10 AND ma10 < ma20)
        WHERE trade_date = :target_date
    """)
    result = session.execute(ma_sql, {'target_date': target_date})
    logger.info(f"  ✓ MA pattern 更新完成，影响 {result.rowcount} 行")

    # 3. MACD pattern（金叉/死叉 + 底背离/顶背离）
    #    修复：使用最近的有效 indicators 日期，而不是强制要求当天
    #    原因：stock_indicators 可能滞后于 stock_daily_snapshot
    macd_sql = text("""
        WITH latest_indicators AS (
            -- 获取每只股票在 target_date 之前最新的 indicators 记录
            SELECT DISTINCT ON (code) code, trade_date, macd, dea, dif, rsi6, rsi24
            FROM stock_indicators
            WHERE cycle = '1d' AND trade_date <= :target_date
            ORDER BY code, trade_date DESC
        ),
        prev_indicators AS (
            -- 获取前一日 indicators（用于金叉/死叉/背离判断）
            SELECT DISTINCT ON (i.code) i.code, 
                   iprev.trade_date, iprev.macd, iprev.dea, iprev.dif, iprev.rsi6, iprev.rsi24
            FROM latest_indicators i
            LEFT JOIN LATERAL (
                SELECT trade_date, macd, dea, dif, rsi6, rsi24
                FROM stock_indicators
                WHERE code = i.code AND cycle = '1d' AND trade_date < i.trade_date
                ORDER BY trade_date DESC LIMIT 1
            ) iprev ON TRUE
        ),
        latest_quotes AS (
            -- 获取 target_date 的行情（用于背离判断）
            SELECT code, close, high, low
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = :target_date
        ),
        prev_quotes AS (
            -- 获取前一日行情
            SELECT DISTINCT ON (code) code, close AS close_prev
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date < :target_date
            ORDER BY code, trade_date DESC
        )
        UPDATE stock_daily_snapshot s
        SET
            -- 金叉（macd 从下向上穿过 dea）
            macd_low_golden_cross = (
                li.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND pi.macd < pi.dea AND li.macd >= li.dea
            ),
            -- 死叉（macd 从上向下穿过 dea）
            macd_high_death_cross = (
                li.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND pi.macd > pi.dea AND li.macd <= li.dea
            ),
            -- 底背离：股价新低，MACD 低点抬高
            macd_bottom_divergence = (
                lq.close IS NOT NULL AND pq.close_prev IS NOT NULL
                AND li.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND lq.close < pq.close_prev
                AND li.macd > pi.macd
            ),
            -- 顶背离：股价新高，MACD 高点降低
            macd_top_divergence = (
                lq.close IS NOT NULL AND pq.close_prev IS NOT NULL
                AND li.macd IS NOT NULL AND pi.macd IS NOT NULL
                AND lq.close > pq.close_prev
                AND li.macd < pi.macd
            )
        FROM latest_indicators li
        LEFT JOIN prev_indicators pi ON li.code = pi.code
        LEFT JOIN latest_quotes lq ON li.code = lq.code
        LEFT JOIN prev_quotes pq ON li.code = pq.code
        WHERE s.code = li.code
          AND s.trade_date = :target_date
    """)
    result = session.execute(macd_sql, {'target_date': target_date})
    logger.info(f"  ✓ MACD pattern 更新完成，影响 {result.rowcount} 行")

    # 4. BOLL pattern（需要前一日收盘价，使用 CTE 避免 LATERAL 引用问题）
    boll_sql = text("""
        WITH prev_close AS (
            SELECT DISTINCT ON (code) code, close AS close_prev
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = (
                SELECT MAX(trade_date) FROM stock_quotes q2
                WHERE q2.code = stock_quotes.code AND q2.cycle = '1d' AND q2.trade_date < :target_date
            )
        )
        UPDATE stock_daily_snapshot s
        SET boll_break_upper = (pc.close_prev IS NOT NULL AND s.close > s.boll_upper AND pc.close_prev <= s.boll_upper),
            boll_break_middle_up = (pc.close_prev IS NOT NULL AND s.close > s.boll_mid AND pc.close_prev <= s.boll_mid),
            boll_break_middle_down = (pc.close_prev IS NOT NULL AND s.close < s.boll_mid AND pc.close_prev >= s.boll_mid),
            boll_break_lower = (pc.close_prev IS NOT NULL AND s.close < s.boll_lower AND pc.close_prev >= s.boll_lower)
        FROM prev_close pc
        WHERE s.trade_date = :target_date AND s.code = pc.code
    """)
    result = session.execute(boll_sql, {'target_date': target_date})
    logger.info(f"  ✓ BOLL pattern 更新完成，影响 {result.rowcount} 行")

    # 5. RSI pattern（金叉/死叉 + 底背离/顶背离）
    #    修复：使用 CTE 获取最近有效 indicators，解决日期不匹配问题
    rsi_sql = text("""
        WITH latest_indicators AS (
            -- 获取每只股票在 target_date 之前最新的 indicators 记录
            SELECT DISTINCT ON (code) code, trade_date, macd, dea, dif, rsi6, rsi24
            FROM stock_indicators
            WHERE cycle = '1d' AND trade_date <= :target_date
            ORDER BY code, trade_date DESC
        ),
        prev_indicators AS (
            -- 获取前一日 indicators（用于金叉/死叉/背离判断）
            SELECT DISTINCT ON (i.code) i.code, 
                   iprev.trade_date, iprev.macd, iprev.dea, iprev.dif, iprev.rsi6, iprev.rsi24
            FROM latest_indicators i
            LEFT JOIN LATERAL (
                SELECT trade_date, macd, dea, dif, rsi6, rsi24
                FROM stock_indicators
                WHERE code = i.code AND cycle = '1d' AND trade_date < i.trade_date
                ORDER BY trade_date DESC LIMIT 1
            ) iprev ON TRUE
        ),
        latest_quotes AS (
            -- 获取 target_date 的行情（用于背离判断）
            SELECT code, close, high, low
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = :target_date
        ),
        prev_quotes AS (
            -- 获取前一日行情
            SELECT DISTINCT ON (code) code, close AS close_prev
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date < :target_date
            ORDER BY code, trade_date DESC
        )
        UPDATE stock_daily_snapshot s
        SET
            -- RSI 低位金叉（rsi6 从下向上穿过 rsi24，且两者均在 30 以下）
            rsi_low_golden_cross = (
                li.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND li.rsi24 IS NOT NULL AND pi.rsi24 IS NOT NULL
                AND li.rsi6 < 30 AND pi.rsi6 < 30
                AND pi.rsi6 <= pi.rsi24 AND li.rsi6 > li.rsi24
            ),
            -- RSI 高位死叉（rsi6 从上向下穿过 rsi24，且两者均在 70 以上）
            rsi_high_death_cross = (
                li.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND li.rsi24 IS NOT NULL AND pi.rsi24 IS NOT NULL
                AND li.rsi6 > 70 AND pi.rsi6 > 70
                AND pi.rsi6 >= pi.rsi24 AND li.rsi6 < li.rsi24
            ),
            -- RSI 底背离：股价新低，RSI6 低点抬高
            rsi_bottom_divergence = (
                lq.close IS NOT NULL AND pq.close_prev IS NOT NULL
                AND li.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND lq.close < pq.close_prev
                AND li.rsi6 > pi.rsi6
            ),
            -- RSI 顶背离：股价新高，RSI6 高点降低
            rsi_top_divergence = (
                lq.close IS NOT NULL AND pq.close_prev IS NOT NULL
                AND li.rsi6 IS NOT NULL AND pi.rsi6 IS NOT NULL
                AND lq.close > pq.close_prev
                AND li.rsi6 < pi.rsi6
            )
        FROM latest_indicators li
        LEFT JOIN prev_indicators pi ON li.code = pi.code
        LEFT JOIN latest_quotes lq ON li.code = lq.code
        LEFT JOIN prev_quotes pq ON li.code = pq.code
        WHERE s.code = li.code
          AND s.trade_date = :target_date
    """)
    result = session.execute(rsi_sql, {'target_date': target_date})
    logger.info(f"  ✓ RSI pattern 更新完成，影响 {result.rowcount} 行")

    session.commit()
    logger.info(f"✅ {target_date} 全部 pattern 更新完成")


def sync_date_range(start_date: str, end_date: str):
    """
    同步日期范围内的所有数据
    
    Args:
        start_date: 开始日期（格式：YYYY-MM-DD）
        end_date: 结束日期（格式：YYYY-MM-DD）
    """
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        try:
            sync_daily_snapshot(date_str)
        except Exception as e:
            logger.warning(f"⚠️ 跳过 {date_str}: {e}")
        current += timedelta(days=1)


def get_latest_trade_date():
    """获取最新交易日期"""
    engine = get_db_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'"))
        row = result.fetchone()
        return row[0].strftime('%Y-%m-%d') if row[0] else None


def main():
    parser = argparse.ArgumentParser(description='股票每日快照宽表同步脚本')
    parser.add_argument('--date', type=str, help='同步指定日期（格式：YYYY-MM-DD）')
    parser.add_argument('--start-date', type=str, help='同步开始日期')
    parser.add_argument('--end-date', type=str, help='同步结束日期')
    parser.add_argument('--latest', action='store_true', help='同步最新交易日数据')
    parser.add_argument('--batch-size', type=int, default=10000, help='批量处理大小')
    
    args = parser.parse_args()
    
    if args.date:
        sync_daily_snapshot(args.date, args.batch_size)
    elif args.start_date and args.end_date:
        sync_date_range(args.start_date, args.end_date)
    elif args.latest:
        latest_date = get_latest_trade_date()
        if latest_date:
            sync_daily_snapshot(latest_date, args.batch_size)
        else:
            logger.error("❌ 未找到最新交易日期")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
