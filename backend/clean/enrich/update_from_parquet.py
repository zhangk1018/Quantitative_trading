#!/usr/bin/env python3
"""从parquet文件更新宽表数据"""

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
    
    # 读取parquet文件
    print("📥 读取parquet文件...")
    df = pd.read_parquet('data/price/daily/latest_quotes.parquet')
    print(f"✅ 文件包含 {len(df)} 条记录")
    
    # 更新 stock_basic 表的行业信息
    print("\n🔄 更新 stock_basic 表（行业信息）...")
    update_count = 0
    with engine.connect() as conn:
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            # 格式: 000001.SZ -> SZ.000001
            if '.SZ' in ts_code:
                code = 'SZ.' + ts_code.replace('.SZ', '')
            elif '.SH' in ts_code:
                code = 'SH.' + ts_code.replace('.SH', '')
            else:
                continue
            
            industry = row.get('industry', '')
            if pd.notna(industry) and industry != '':
                conn.execute(
                    text("""
                        UPDATE stock_basic 
                        SET industry = :industry 
                        WHERE code = :code
                    """),
                    {'industry': industry, 'code': code}
                )
                update_count += 1
        
        conn.commit()
    print(f"✅ 更新了 {update_count} 条行业信息")
    
    # 直接更新宽表的所有字段
    print("\n🔄 直接更新宽表 stock_daily_snapshot...")
    update_count = 0
    with engine.connect() as conn:
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            code = ts_code.replace('.SZ', '').replace('.SH', '')
            
            # 收集要更新的字段
            update_fields = []
            params = {'code': code}
            
            # 行业
            industry = row.get('industry')
            if pd.notna(industry) and industry != '':
                update_fields.append('industry = :industry')
                params['industry'] = industry
            
            # PE
            pe = row.get('pe')
            if pd.notna(pe):
                update_fields.append('pe = :pe')
                params['pe'] = float(pe)
            
            # PB
            pb = row.get('pb')
            if pd.notna(pb):
                update_fields.append('pb = :pb')
                params['pb'] = float(pb)
            
            # 换手率
            turnover_rate = row.get('turnover_rate')
            if pd.notna(turnover_rate):
                update_fields.append('turnover_rate = :turnover_rate')
                params['turnover_rate'] = float(turnover_rate)
            
            # 总市值
            total_mv = row.get('total_mv')
            if pd.notna(total_mv):
                update_fields.append('market_cap = :market_cap')
                params['market_cap'] = float(total_mv)
            
            # 流通市值
            circ_mv = row.get('circ_mv')
            if pd.notna(circ_mv):
                update_fields.append('circ_mv = :circ_mv')
                params['circ_mv'] = float(circ_mv)
            
            if update_fields:
                sql = f"""
                    UPDATE stock_daily_snapshot 
                    SET {', '.join(update_fields)}
                    WHERE code = :code AND trade_date = '2026-06-01'
                """
                conn.execute(text(sql), params)
                update_count += 1
        
        conn.commit()
    print(f"✅ 更新了 {update_count} 条宽表记录")
    
    # 更新宽表中的行业（从stock_basic）
    print("\n🔄 从stock_basic同步行业到宽表...")
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE stock_daily_snapshot s
            SET industry = b.industry
            FROM stock_basic b
            WHERE RIGHT(b.code, 6) = s.code AND s.trade_date = '2026-06-01'
              AND b.industry IS NOT NULL AND b.industry != ''
              AND (s.industry IS NULL OR s.industry = '')
        """))
        conn.commit()
    
    print("✅ 宽表更新完成")
    
    # 验证结果
    print("\n📊 验证数据...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 ELSE 0 END) as industry_count,
                SUM(CASE WHEN pe IS NOT NULL THEN 1 ELSE 0 END) as pe_count,
                SUM(CASE WHEN pb IS NOT NULL THEN 1 ELSE 0 END) as pb_count,
                SUM(CASE WHEN turnover_rate IS NOT NULL THEN 1 ELSE 0 END) as turnover_count,
                SUM(CASE WHEN market_cap IS NOT NULL THEN 1 ELSE 0 END) as market_cap_count
            FROM stock_daily_snapshot 
            WHERE trade_date = '2026-06-01'
        """))
        row = result.mappings().first()
        
        print(f"总记录数: {row['total']}")
        print(f"行业非空: {row['industry_count']}")
        print(f"PE非空: {row['pe_count']}")
        print(f"PB非空: {row['pb_count']}")
        print(f"换手率非空: {row['turnover_count']}")
        print(f"总市值非空: {row['market_cap_count']}")

if __name__ == '__main__':
    main()
