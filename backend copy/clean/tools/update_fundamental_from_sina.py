#!/usr/bin/env python3
"""从新浪数据源更新基本面数据（PE、换手率等）"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pandas as pd
from sqlalchemy import create_engine, text
from utils.config import load_config
from collector.datasource.sina import SinaDataSource

def main():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)
    
    # 从新浪数据源获取实时行情数据
    print("📡 从新浪数据源获取实时行情...")
    ds = SinaDataSource()
    if not ds.connect():
        print("❌ 无法连接新浪数据源")
        return
    
    df_sina = ds.fetch_market_snapshot()
    if df_sina is None or df_sina.empty:
        print("❌ 未获取到数据")
        return
    
    print(f"✅ 获取到 {len(df_sina)} 条数据")
    
    # 更新 stock_fundamental_pit 表
    print("\n📥 更新 stock_fundamental_pit 表...")
    trade_date = '2026-06-01'  # 使用测试日期
    updated_count = 0
    
    with engine.connect() as conn:
        for _, row in df_sina.iterrows():
            code = row['code'].replace('sz.', '').replace('sh.', '')
            
            # 只有有效数据才更新
            if pd.notna(row['pe']) and pd.notna(row['turnover_rate']):
                conn.execute(
                    text("""
                        INSERT INTO stock_fundamental_pit
                        (code, report_date, announce_date, pe_ttm, turnover_rate)
                        VALUES (:code, :report_date, :announce_date, :pe, :turnover_rate)
                        ON CONFLICT (code, report_date)
                        DO UPDATE SET
                            pe_ttm = EXCLUDED.pe_ttm,
                            turnover_rate = EXCLUDED.turnover_rate
                    """),
                    {
                        'code': code,
                        'report_date': trade_date,
                        'announce_date': trade_date,
                        'pe': float(row['pe']),
                        'turnover_rate': float(row['turnover_rate'])
                    }
                )
                updated_count += 1
        
        conn.commit()
    
    print(f"✅ 更新了 {updated_count} 条基本面数据")
    
    # 更新宽表
    print("\n🔄 更新宽表 stock_daily_snapshot...")
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE stock_daily_snapshot s
            SET 
                pe = f.pe_ttm,
                turnover_rate = f.turnover_rate
            FROM stock_fundamental_pit f
            WHERE s.code = f.code AND s.trade_date = f.report_date
              AND f.report_date = '2026-06-01'
        """))
        conn.commit()
        updated = conn.execute(text("SELECT row_count FROM pg_stat_get_last_autovacuum('stock_daily_snapshot')")).scalar()
    
    print("✅ 宽表更新完成")
    
    # 验证结果
    print("\n📊 验证数据...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) 
            FROM stock_daily_snapshot 
            WHERE trade_date = '2026-06-01' AND pe IS NOT NULL
        """))
        count = result.scalar_one()
        print(f"宽表中 PE 非空的记录数: {count}")
    
    ds.disconnect()

if __name__ == '__main__':
    main()
