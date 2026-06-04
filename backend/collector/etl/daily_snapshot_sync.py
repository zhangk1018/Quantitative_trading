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
from datetime import datetime, timedelta

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from collector.db.models import StockDailySnapshot, Base


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
        print(f"🔄 开始同步 {target_date} 的宽表数据...")
        
        # 1. 使用 SQL 计算并插入/更新（利用数据库计算能力）
        # PostgreSQL UPSERT 语法：INSERT ... ON CONFLICT DO UPDATE
        upsert_sql = text("""
            INSERT INTO stock_daily_snapshot (
                code, stock_name, listed_board, industry, sub_industry,
                trade_date, open, high, low, close, pre_close, volume, amount, adjust_type,
                change, change_pct, ma5, ma10, ma20, rsi_6, macd,
                is_st, is_new, limit_up, limit_down
            )
            SELECT 
                q.code,
                COALESCE(b.name, '') AS stock_name,
                CASE 
                    WHEN q.code LIKE '60%' THEN '主板'
                    WHEN q.code LIKE '000%' THEN '主板'
                    WHEN q.code LIKE '002%' THEN '中小板'
                    WHEN q.code LIKE '300%' THEN '创业板'
                    WHEN q.code LIKE '688%' THEN '科创板'
                    ELSE '其他'
                END AS listed_board,
                COALESCE(b.industry, '') AS industry,
                COALESCE(b.industry, '') AS sub_industry,
                q.trade_date,
                q.open,
                q.high,
                q.low,
                q.close,
                q.pre_close,
                q.volume,
                q.amount,
                q.adjust_type,
                ROUND(q.close - q.pre_close, 2) AS change,
                ROUND((q.close - q.pre_close) / NULLIF(q.pre_close, 0) * 100, 2) AS change_pct,
                i.ma5,
                i.ma10,
                i.ma20,
                i.rsi6 AS rsi_6,
                i.macd,
                FALSE AS is_st,
                FALSE AS is_new,
                FALSE AS limit_up,
                FALSE AS limit_down
            FROM stock_quotes q
            LEFT JOIN stock_basic b ON q.code = b.code
            LEFT JOIN stock_indicators i ON q.code = i.code AND q.trade_date = i.trade_date AND q.cycle = i.cycle
            WHERE q.cycle = '1d' AND q.trade_date = :target_date
            ON CONFLICT (code, trade_date) DO UPDATE SET
                stock_name = EXCLUDED.stock_name,
                listed_board = EXCLUDED.listed_board,
                industry = EXCLUDED.industry,
                sub_industry = EXCLUDED.sub_industry,
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
                ma5 = EXCLUDED.ma5,
                ma10 = EXCLUDED.ma10,
                ma20 = EXCLUDED.ma20,
                rsi_6 = EXCLUDED.rsi_6,
                macd = EXCLUDED.macd,
                updated_at = CURRENT_TIMESTAMP
        """)
        
        result = session.execute(upsert_sql, {'target_date': target_date})
        session.commit()
        
        print(f"✅ {target_date} 宽表同步完成，影响 {result.rowcount} 条记录")
        
    except Exception as e:
        session.rollback()
        print(f"❌ {target_date} 同步失败: {e}")
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
            print(f"⚠️ 跳过 {date_str}: {e}")
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
            print("❌ 未找到最新交易日期")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
