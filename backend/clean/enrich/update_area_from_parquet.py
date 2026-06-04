#!/usr/bin/env python3
"""从parquet文件更新地区字段"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pandas as pd
from sqlalchemy import create_engine, text
from utils.config import load_config

def main():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)
    
    # 先检查宽表是否有area字段，如果没有则添加
    print("🔍 检查宽表结构...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_name='stock_daily_snapshot' AND column_name='area'
        """))
        has_area = result.scalar() > 0
        
        if not has_area:
            print("  添加area字段到宽表...")
            conn.execute(text("ALTER TABLE stock_daily_snapshot ADD COLUMN area VARCHAR(50)"))
            conn.commit()
        else:
            print("  area字段已存在")
    
    # 更新地区数据
    print("\n📥 读取parquet文件...")
    df = pd.read_parquet('data/price/daily/latest_quotes.parquet')
    print(f"✅ 文件包含 {len(df)} 条记录")
    
    print("\n🔄 更新宽表地区字段...")
    update_count = 0
    
    with engine.connect() as conn:
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            code = ts_code.replace('.SZ', '').replace('.SH', '')
            area = row.get('area')
            
            if pd.notna(area) and area != '' and area != '-':
                conn.execute(
                    text("UPDATE stock_daily_snapshot SET area = :area WHERE code = :code AND trade_date = '2026-06-01'"),
                    {'area': area, 'code': code}
                )
                update_count += 1
        
        conn.commit()
    
    print(f"✅ 更新了 {update_count} 条地区数据")
    
    # 验证结果
    print("\n📊 验证地区数据...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN area IS NOT NULL AND area != '' THEN 1 ELSE 0 END) as area_count,
                COUNT(DISTINCT area) as distinct_count
            FROM stock_daily_snapshot 
            WHERE trade_date = '2026-06-01'
        """))
        row = result.mappings().first()
        
        print(f"总记录数: {row['total']}")
        print(f"地区非空: {row['area_count']}")
        print(f"地区种类: {row['distinct_count']}")
        
        # 显示地区分布
        result = conn.execute(text("""
            SELECT area, COUNT(*) as count 
            FROM stock_daily_snapshot 
            WHERE trade_date = '2026-06-01' AND area IS NOT NULL AND area != ''
            GROUP BY area 
            ORDER BY count DESC
        """))
        print("\n地区分布:")
        for row in result.fetchall():
            print(f"  {row[0]}: {row[1]}只")

if __name__ == '__main__':
    main()
