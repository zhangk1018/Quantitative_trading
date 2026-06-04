#!/usr/bin/env python3
"""更新ST、新股、涨停、跌停标志"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from sqlalchemy import create_engine, text
from utils.config import load_config
from datetime import datetime, timedelta

def main():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)
    
    print("🔄 更新ST、新股、涨停、跌停标志...")
    
    with engine.connect() as conn:
        # 1. 更新ST标志（从stock_basic获取）
        print("  更新ST标志...")
        conn.execute(text("""
            UPDATE stock_daily_snapshot s
            SET is_st = CASE WHEN b.name LIKE '%ST%' THEN true ELSE false END
            FROM stock_basic b
            WHERE RIGHT(b.code, 6) = s.code
              AND s.trade_date = '2026-06-01'
        """))
        
        # 2. 更新新股标志（上市日期在最近90天内）
        print("  更新新股标志...")
        conn.execute(text("""
            UPDATE stock_daily_snapshot s
            SET is_new = CASE WHEN b.list_date >= '2026-03-04' THEN true ELSE false END
            FROM stock_basic b
            WHERE RIGHT(b.code, 6) = s.code
              AND s.trade_date = '2026-06-01'
        """))
        
        # 3. 更新涨停标志（ST股5%，非ST股10%）
        print("  更新涨停标志...")
        conn.execute(text("""
            UPDATE stock_daily_snapshot s
            SET limit_up = CASE 
                WHEN s.is_st = true AND s.change_pct >= 4.9 THEN true
                WHEN s.is_st = false AND s.change_pct >= 9.9 THEN true
                ELSE false 
            END
            WHERE s.trade_date = '2026-06-01'
        """))
        
        # 4. 更新跌停标志（ST股-5%，非ST股-10%）
        print("  更新跌停标志...")
        conn.execute(text("""
            UPDATE stock_daily_snapshot s
            SET limit_down = CASE 
                WHEN s.is_st = true AND s.change_pct <= -4.9 THEN true
                WHEN s.is_st = false AND s.change_pct <= -9.9 THEN true
                ELSE false 
            END
            WHERE s.trade_date = '2026-06-01'
        """))
        
        conn.commit()
    
    # 验证结果
    print("\n📊 验证标志数据...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_st = true THEN 1 ELSE 0 END) as st_count,
                SUM(CASE WHEN is_new = true THEN 1 ELSE 0 END) as new_count,
                SUM(CASE WHEN limit_up = true THEN 1 ELSE 0 END) as up_count,
                SUM(CASE WHEN limit_down = true THEN 1 ELSE 0 END) as down_count
            FROM stock_daily_snapshot 
            WHERE trade_date = '2026-06-01'
        """))
        row = result.mappings().first()
        
        print(f"总记录数: {row['total']}")
        print(f"ST股数量: {row['st_count']}")
        print(f"新股数量: {row['new_count']}")
        print(f"涨停数量: {row['up_count']}")
        print(f"跌停数量: {row['down_count']}")

if __name__ == '__main__':
    main()
