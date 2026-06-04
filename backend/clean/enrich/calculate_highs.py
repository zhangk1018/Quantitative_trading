#!/usr/bin/env python3
"""
计算20日新高、60日新高、120日新高和250日新高

使用股票的历史收盘价数据，判断每只股票在指定日期是否达到：
- 20日新高：收盘价高于过去20个交易日的最高收盘价
- 60日新高：收盘价高于过去60个交易日的最高收盘价
- 120日新高：收盘价高于过去120个交易日的最高收盘价
- 250日新高：收盘价高于过去250个交易日的最高收盘价

调用方式：
    python scripts/enrichment/calculate_highs.py
    python scripts/enrichment/calculate_highs.py --date 2026-06-01
"""

import argparse
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'src'))

from sqlalchemy import create_engine, text
from utils.config import load_config

def calculate_highs(date_str=None):
    """计算新高（20/60/120/250日）"""
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)
    
    # 使用指定日期或最新日期
    if not date_str:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT MAX(trade_date) FROM stock_quotes"))
            date_str = result.scalar()
            if date_str:
                date_str = date_str.strftime('%Y-%m-%d')
            else:
                print("❌ 无法获取最新日期")
                return
    
    print(f"📅 计算日期: {date_str}")
    
    # 确保数据库表有 break_high_120/250 字段
    with engine.connect() as conn:
        for col_name, col_type in [('break_high_120', 'BOOLEAN'), ('break_high_250', 'BOOLEAN')]:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name='stock_daily_snapshot' AND column_name=:name
            """), {'name': col_name})
            if result.scalar() == 0:
                print(f"  添加字段: {col_name} ({col_type})")
                conn.execute(text(f"ALTER TABLE stock_daily_snapshot ADD COLUMN {col_name} {col_type} DEFAULT FALSE"))
        conn.commit()
    
    with engine.connect() as conn:
        # 获取所有股票代码
        result = conn.execute(text("SELECT DISTINCT code FROM stock_quotes WHERE trade_date <= :date"), {'date': date_str})
        codes = [row[0] for row in result.fetchall()]
        
        print(f"📊 处理股票数量: {len(codes)}")
        
        updated_count = 0
        for code in codes:
            # 获取过去20个交易日的收盘价
            result = conn.execute(text("""
                SELECT close FROM stock_quotes 
                WHERE code = :code AND trade_date <= :date 
                ORDER BY trade_date DESC 
                LIMIT 20
            """), {'code': code, 'date': date_str})
            prices_20 = [row[0] for row in result.fetchall() if row[0] is not None]
            
            # 获取过去60个交易日的收盘价
            result = conn.execute(text("""
                SELECT close FROM stock_quotes 
                WHERE code = :code AND trade_date <= :date 
                ORDER BY trade_date DESC 
                LIMIT 60
            """), {'code': code, 'date': date_str})
            prices_60 = [row[0] for row in result.fetchall() if row[0] is not None]
            
            # 获取过去120个交易日的收盘价
            result = conn.execute(text("""
                SELECT close FROM stock_quotes 
                WHERE code = :code AND trade_date <= :date 
                ORDER BY trade_date DESC 
                LIMIT 120
            """), {'code': code, 'date': date_str})
            prices_120 = [row[0] for row in result.fetchall() if row[0] is not None]
            
            # 获取过去250个交易日的收盘价
            result = conn.execute(text("""
                SELECT close FROM stock_quotes 
                WHERE code = :code AND trade_date <= :date 
                ORDER BY trade_date DESC 
                LIMIT 250
            """), {'code': code, 'date': date_str})
            prices_250 = [row[0] for row in result.fetchall() if row[0] is not None]
            
            # 获取当日收盘价
            result = conn.execute(text("""
                SELECT close FROM stock_quotes 
                WHERE code = :code AND trade_date = :date
            """), {'code': code, 'date': date_str})
            today_close = result.scalar()
            
            if today_close is None:
                continue
            
            # 判断是否为新高
            break_high_20 = False
            break_high_60 = False
            break_high_120 = False
            break_high_250 = False
            
            if len(prices_20) >= 20:
                high_20 = max(prices_20[1:])  # 排除今日
                break_high_20 = today_close > high_20
            
            if len(prices_60) >= 60:
                high_60 = max(prices_60[1:])  # 排除今日
                break_high_60 = today_close > high_60
            
            if len(prices_120) >= 120:
                high_120 = max(prices_120[1:])  # 排除今日
                break_high_120 = today_close > high_120
            
            if len(prices_250) >= 250:
                high_250 = max(prices_250[1:])  # 排除今日
                break_high_250 = today_close > high_250
            
            # 更新宽表
            conn.execute(text("""
                UPDATE stock_daily_snapshot 
                SET break_high_20 = :high_20, break_high_60 = :high_60,
                    break_high_120 = :high_120, break_high_250 = :high_250
                WHERE code = :code AND trade_date = :date
            """), {
                'code': code,
                'date': date_str,
                'high_20': break_high_20,
                'high_60': break_high_60,
                'high_120': break_high_120,
                'high_250': break_high_250
            })
            
            updated_count += 1
        
        conn.commit()
        print(f"✅ 更新了 {updated_count} 条记录")
        
        # 验证结果
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN break_high_20 = TRUE THEN 1 ELSE 0 END) as high_20_count,
                SUM(CASE WHEN break_high_60 = TRUE THEN 1 ELSE 0 END) as high_60_count,
                SUM(CASE WHEN break_high_120 = TRUE THEN 1 ELSE 0 END) as high_120_count,
                SUM(CASE WHEN break_high_250 = TRUE THEN 1 ELSE 0 END) as high_250_count
            FROM stock_daily_snapshot 
            WHERE trade_date = :date
        """), {'date': date_str})
        row = result.mappings().first()
        
        print(f"\n📊 统计结果 ({date_str}):")
        print(f"总记录数: {row.total}")
        print(f"20日新高: {row.high_20_count} 只")
        print(f"60日新高: {row.high_60_count} 只")
        print(f"120日新高: {row.high_120_count} 只")
        print(f"250日新高: {row.high_250_count} 只")

def main():
    parser = argparse.ArgumentParser(description='计算20日新高和60日新高')
    parser.add_argument('--date', type=str, help='指定日期（格式：YYYY-MM-DD）')
    
    args = parser.parse_args()
    calculate_highs(args.date)

if __name__ == '__main__':
    main()
