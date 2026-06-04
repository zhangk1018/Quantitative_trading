#!/usr/bin/env python3
"""
batch_sync.py - 宽表全量同步脚本（分批处理）

用于将历史数据同步到 stock_daily_snapshot 宽表，
支持按年份分批处理，避免一次性处理过大数据量。
"""

import os
import sys
import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text


def get_db_engine():
    """获取数据库引擎"""
    from collector.db.database import DATABASE_URL
    return create_engine(DATABASE_URL)


def get_date_range():
    """获取需要同步的日期范围"""
    engine = get_db_engine()
    with engine.connect() as conn:
        # 获取 stock_quotes 中的日期范围
        result = conn.execute(text("""
            SELECT MIN(trade_date), MAX(trade_date) 
            FROM stock_quotes 
            WHERE cycle = '1d'
        """))
        row = result.fetchone()
        min_date, max_date = row[0], row[1]
        
        # 获取已同步的最大日期
        result = conn.execute(text("SELECT MAX(trade_date) FROM stock_daily_snapshot"))
        row = result.fetchone()
        last_sync_date = row[0]
        
    return min_date, max_date, last_sync_date


def sync_batch(start_date, end_date):
    """同步指定日期范围的数据"""
    engine = get_db_engine()
    
    try:
        with engine.begin() as conn:
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
                WHERE q.cycle = '1d' 
                  AND q.trade_date >= :start_date 
                  AND q.trade_date <= :end_date
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
            
            result = conn.execute(upsert_sql, {'start_date': start_date, 'end_date': end_date})
            return result.rowcount
            
    except Exception as e:
        print(f"❌ 同步失败: {e}")
        raise


def main():
    print("============================================")
    print("宽表全量同步脚本")
    print("============================================")
    
    min_date, max_date, last_sync_date = get_date_range()
    print(f"数据源日期范围: {min_date} ~ {max_date}")
    print(f"已同步到: {last_sync_date or '未同步'}")
    
    # 强制全量同步：从最早日期开始
    start_date = min_date
    
    # 确保 start_date 是 date 类型
    if hasattr(start_date, 'date'):
        start_date = start_date.date()
    
    print(f"待同步日期范围: {start_date} ~ {max_date}")
    
    # 按年份分批同步
    current_date = start_date
    total_rows = 0
    batch_num = 0
    
    while current_date <= max_date:
        # 每批处理一年的数据
        batch_end = min(current_date.replace(month=12, day=31), max_date)
        
        batch_num += 1
        print(f"\n📦 批次 {batch_num}: {current_date} ~ {batch_end}")
        
        start_time = datetime.datetime.now()
        row_count = sync_batch(current_date, batch_end)
        elapsed = datetime.datetime.now() - start_time
        
        total_rows += row_count
        print(f"✅ 同步完成: {row_count:,} 条记录, 耗时: {elapsed.total_seconds():.1f}秒")
        
        current_date = batch_end + datetime.timedelta(days=1)
    
    print("\n============================================")
    print(f"🎉 全量同步完成!")
    print(f"总同步记录数: {total_rows:,}")
    print("============================================")


if __name__ == '__main__':
    main()
