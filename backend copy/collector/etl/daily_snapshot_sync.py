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
                AND i.trade_date = (SELECT MAX(trade_date) FROM stock_indicators WHERE code = q.code AND trade_date <= :target_date)
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
        
        logger.info(f"✅ {target_date} 宽表同步完成，影响 {result.rowcount} 条记录")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ {target_date} 同步失败: {e}")
        raise
    finally:
        session.close()


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
