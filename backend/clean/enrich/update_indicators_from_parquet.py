#!/usr/bin/env python3
"""从parquet文件更新技术指标数据"""

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
    
    # 更新宽表的技术指标字段
    print("\n🔄 更新宽表技术指标...")
    update_count = 0
    
    with engine.connect() as conn:
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            code = ts_code.replace('.SZ', '').replace('.SH', '')
            
            # 收集要更新的字段
            update_fields = []
            params = {'code': code}
            
            # RSI6
            rsi_6 = row.get('rsi_6')
            if pd.notna(rsi_6):
                update_fields.append('rsi_6 = :rsi_6')
                params['rsi_6'] = float(rsi_6)
            
            # MACD
            macd = row.get('macd')
            if pd.notna(macd):
                update_fields.append('macd = :macd')
                params['macd'] = float(macd)
            
            # 布林上轨
            boll_upper = row.get('boll_upper')
            if pd.notna(boll_upper):
                update_fields.append('boll_upper = :boll_upper')
                params['boll_upper'] = float(boll_upper)
            
            # 布林中轨
            boll_mid = row.get('boll_mid')
            if pd.notna(boll_mid):
                update_fields.append('boll_mid = :boll_mid')
                params['boll_mid'] = float(boll_mid)
            
            # 布林下轨
            boll_lower = row.get('boll_lower')
            if pd.notna(boll_lower):
                update_fields.append('boll_lower = :boll_lower')
                params['boll_lower'] = float(boll_lower)
            
            if update_fields:
                sql = f"""
                    UPDATE stock_daily_snapshot 
                    SET {', '.join(update_fields)}
                    WHERE code = :code AND trade_date = '2026-04-20'
                """
                conn.execute(text(sql), params)
                update_count += 1
        
        conn.commit()
    
    print(f"✅ 更新了 {update_count} 条技术指标数据")
    
    # 计算并更新MA5, MA10, MA20和5日均量
    print("\n🔄 计算并更新均线指标...")
    
    # 从stock_quotes获取历史数据计算均线
    with engine.connect() as conn:
        # 获取股票列表
        result = conn.execute(text("SELECT DISTINCT code FROM stock_daily_snapshot WHERE trade_date = '2026-04-20'"))
        codes = [row[0] for row in result.fetchall()]
        
        for code in codes:
            # 获取最近20个交易日的数据
            result = conn.execute(
                text("""
                    SELECT trade_date, close, volume 
                    FROM stock_quotes 
                    WHERE code = :code AND cycle = '1d'
                    ORDER BY trade_date DESC 
                    LIMIT 20
                """),
                {'code': code}
            )
            rows = result.fetchall()
            
            if len(rows) >= 5:
                closes = [float(row[1]) for row in rows]
                volumes = [int(row[2]) for row in rows]
                
                # 计算MA5
                ma5 = sum(closes[:5]) / 5 if len(closes) >= 5 else None
                
                # 计算MA10
                ma10 = sum(closes[:10]) / 10 if len(closes) >= 10 else None
                
                # 计算MA20
                ma20 = sum(closes[:20]) / 20 if len(closes) >= 20 else None
                
                # 计算5日均量
                v_ma5 = int(sum(volumes[:5]) / 5) if len(volumes) >= 5 else None
                
                # 更新宽表
                update_fields = []
                params = {'code': code}
                
                if ma5:
                    update_fields.append('ma5 = :ma5')
                    params['ma5'] = round(ma5, 2)
                
                if ma10:
                    update_fields.append('ma10 = :ma10')
                    params['ma10'] = round(ma10, 2)
                
                if ma20:
                    update_fields.append('ma20 = :ma20')
                    params['ma20'] = round(ma20, 2)
                
                if v_ma5:
                    update_fields.append('v_ma5 = :v_ma5')
                    params['v_ma5'] = v_ma5
                
                if update_fields:
                    sql = f"""
                        UPDATE stock_daily_snapshot 
                        SET {', '.join(update_fields)}
                        WHERE code = :code AND trade_date = '2026-04-20'
                    """
                    conn.execute(text(sql), params)
        
        conn.commit()
    
    print("✅ 均线指标计算完成")
    
    # 验证结果
    print("\n📊 验证技术指标数据...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN ma5 IS NOT NULL THEN 1 ELSE 0 END) as ma5_count,
                SUM(CASE WHEN ma10 IS NOT NULL THEN 1 ELSE 0 END) as ma10_count,
                SUM(CASE WHEN ma20 IS NOT NULL THEN 1 ELSE 0 END) as ma20_count,
                SUM(CASE WHEN v_ma5 IS NOT NULL THEN 1 ELSE 0 END) as v_ma5_count,
                SUM(CASE WHEN rsi_6 IS NOT NULL THEN 1 ELSE 0 END) as rsi6_count,
                SUM(CASE WHEN macd IS NOT NULL THEN 1 ELSE 0 END) as macd_count,
                SUM(CASE WHEN boll_upper IS NOT NULL THEN 1 ELSE 0 END) as boll_count
            FROM stock_daily_snapshot 
            WHERE trade_date = '2026-04-20'
        """))
        row = result.mappings().first()
        
        print(f"总记录数: {row['total']}")
        print(f"MA5非空: {row['ma5_count']}")
        print(f"MA10非空: {row['ma10_count']}")
        print(f"MA20非空: {row['ma20_count']}")
        print(f"5日均量非空: {row['v_ma5_count']}")
        print(f"RSI6非空: {row['rsi6_count']}")
        print(f"MACD非空: {row['macd_count']}")
        print(f"布林带非空: {row['boll_count']}")

if __name__ == '__main__':
    main()
