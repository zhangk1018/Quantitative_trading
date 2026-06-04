#!/usr/bin/env python3
"""从parquet文件更新所有缺失字段到宽表"""

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
    
    # 定义需要添加的字段及其类型
    new_columns = [
        ('volume_ratio', 'NUMERIC(8,2)'),        # 量比
        ('net_mf_amount', 'NUMERIC(18,2)'),      # 净流入(万)
        ('pe_ttm', 'NUMERIC(10,2)'),             # PE-TTM
        ('ps', 'NUMERIC(10,2)'),                 # PS
        ('ps_ttm', 'NUMERIC(10,2)'),             # PS-TTM
        ('dv_ratio', 'NUMERIC(8,4)'),             # 股息率
        ('dv_ttm', 'NUMERIC(8,4)'),              # 股息率TTM
        ('float_share', 'NUMERIC(18,2)'),         # 流通股(万)
        ('buy_sm_amount', 'NUMERIC(18,2)'),       # 小单买
        ('sell_sm_amount', 'NUMERIC(18,2)'),      # 小单卖
        ('buy_md_amount', 'NUMERIC(18,2)'),       # 中单买
        ('sell_md_amount', 'NUMERIC(18,2)'),      # 中单卖
        ('buy_lg_amount', 'NUMERIC(18,2)'),       # 大单买
        ('sell_lg_amount', 'NUMERIC(18,2)'),      # 大单卖
        ('buy_elg_amount', 'NUMERIC(18,2)'),      # 特大买
        ('sell_elg_amount', 'NUMERIC(18,2)'),     # 特大卖
        ('break_high_20', 'BOOLEAN'),             # 20日新高
        ('break_high_60', 'BOOLEAN'),             # 60日新高
        ('break_high_120', 'BOOLEAN'),            # 120日新高
        ('break_high_250', 'BOOLEAN'),            # 250日新高
        ('consec_up_days', 'INTEGER'),            # 连涨天
        ('vol_ratio_5', 'NUMERIC(8,2)'),          # 5日量比
    ]
    
    # 检查并添加缺失字段
    print("🔍 检查并添加缺失字段...")
    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name='stock_daily_snapshot' AND column_name=:name
            """), {'name': col_name})
            if result.scalar() == 0:
                print(f"  添加字段: {col_name} ({col_type})")
                conn.execute(text(f"ALTER TABLE stock_daily_snapshot ADD COLUMN {col_name} {col_type}"))
        
        conn.commit()
    
    # 更新数据
    print("\n📥 读取parquet文件...")
    df = pd.read_parquet('data/price/daily/latest_quotes.parquet')
    print(f"✅ 文件包含 {len(df)} 条记录")
    
    print("\n🔄 更新宽表数据...")
    update_count = 0
    
    with engine.connect() as conn:
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            code = ts_code.replace('.SZ', '').replace('.SH', '')
            
            # 收集要更新的字段
            update_fields = []
            params = {'code': code}
            
            # 量比
            volume_ratio = row.get('volume_ratio')
            if pd.notna(volume_ratio):
                update_fields.append('volume_ratio = :volume_ratio')
                params['volume_ratio'] = round(float(volume_ratio), 2)
            
            # 净流入(万)
            net_mf_amount = row.get('net_mf_amount')
            if pd.notna(net_mf_amount):
                update_fields.append('net_mf_amount = :net_mf_amount')
                params['net_mf_amount'] = round(float(net_mf_amount), 2)
            
            # PE-TTM
            pe_ttm = row.get('pe_ttm')
            if pd.notna(pe_ttm):
                update_fields.append('pe_ttm = :pe_ttm')
                params['pe_ttm'] = round(float(pe_ttm), 2)
            
            # PS
            ps = row.get('ps')
            if pd.notna(ps):
                update_fields.append('ps = :ps')
                params['ps'] = round(float(ps), 2)
            
            # PS-TTM
            ps_ttm = row.get('ps_ttm')
            if pd.notna(ps_ttm):
                update_fields.append('ps_ttm = :ps_ttm')
                params['ps_ttm'] = round(float(ps_ttm), 2)
            
            # 股息率
            dv_ratio = row.get('dv_ratio')
            if pd.notna(dv_ratio):
                update_fields.append('dv_ratio = :dv_ratio')
                params['dv_ratio'] = round(float(dv_ratio), 4)
            
            # 股息率TTM
            dv_ttm = row.get('dv_ttm')
            if pd.notna(dv_ttm):
                update_fields.append('dv_ttm = :dv_ttm')
                params['dv_ttm'] = round(float(dv_ttm), 4)
            
            # 流通股(万)
            float_share = row.get('float_share')
            if pd.notna(float_share):
                update_fields.append('float_share = :float_share')
                params['float_share'] = round(float(float_share), 2)
            
            # 小单买
            buy_sm_amount = row.get('buy_sm_amount')
            if pd.notna(buy_sm_amount):
                update_fields.append('buy_sm_amount = :buy_sm_amount')
                params['buy_sm_amount'] = round(float(buy_sm_amount), 2)
            
            # 小单卖
            sell_sm_amount = row.get('sell_sm_amount')
            if pd.notna(sell_sm_amount):
                update_fields.append('sell_sm_amount = :sell_sm_amount')
                params['sell_sm_amount'] = round(float(sell_sm_amount), 2)
            
            # 中单买
            buy_md_amount = row.get('buy_md_amount')
            if pd.notna(buy_md_amount):
                update_fields.append('buy_md_amount = :buy_md_amount')
                params['buy_md_amount'] = round(float(buy_md_amount), 2)
            
            # 中单卖
            sell_md_amount = row.get('sell_md_amount')
            if pd.notna(sell_md_amount):
                update_fields.append('sell_md_amount = :sell_md_amount')
                params['sell_md_amount'] = round(float(sell_md_amount), 2)
            
            # 大单买
            buy_lg_amount = row.get('buy_lg_amount')
            if pd.notna(buy_lg_amount):
                update_fields.append('buy_lg_amount = :buy_lg_amount')
                params['buy_lg_amount'] = round(float(buy_lg_amount), 2)
            
            # 大单卖
            sell_lg_amount = row.get('sell_lg_amount')
            if pd.notna(sell_lg_amount):
                update_fields.append('sell_lg_amount = :sell_lg_amount')
                params['sell_lg_amount'] = round(float(sell_lg_amount), 2)
            
            # 特大买
            buy_elg_amount = row.get('buy_elg_amount')
            if pd.notna(buy_elg_amount):
                update_fields.append('buy_elg_amount = :buy_elg_amount')
                params['buy_elg_amount'] = round(float(buy_elg_amount), 2)
            
            # 特大卖
            sell_elg_amount = row.get('sell_elg_amount')
            if pd.notna(sell_elg_amount):
                update_fields.append('sell_elg_amount = :sell_elg_amount')
                params['sell_elg_amount'] = round(float(sell_elg_amount), 2)
            
            # 20日新高
            break_high_20 = row.get('break_high_20')
            if pd.notna(break_high_20):
                update_fields.append('break_high_20 = :break_high_20')
                params['break_high_20'] = bool(break_high_20)
            
            # 60日新高
            break_high_60 = row.get('break_high_60')
            if pd.notna(break_high_60):
                update_fields.append('break_high_60 = :break_high_60')
                params['break_high_60'] = bool(break_high_60)
            
            # 连涨天
            consec_up_days = row.get('consec_up_days')
            if pd.notna(consec_up_days):
                update_fields.append('consec_up_days = :consec_up_days')
                params['consec_up_days'] = int(consec_up_days)
            
            # 5日量比
            vol_ratio_5 = row.get('vol_ratio_5')
            if pd.notna(vol_ratio_5):
                update_fields.append('vol_ratio_5 = :vol_ratio_5')
                params['vol_ratio_5'] = round(float(vol_ratio_5), 2)
            
            if update_fields:
                sql = f"""
                    UPDATE stock_daily_snapshot 
                    SET {', '.join(update_fields)}
                    WHERE code = :code AND trade_date = '2026-06-01'
                """
                conn.execute(text(sql), params)
                update_count += 1
        
        conn.commit()
    
    print(f"✅ 更新了 {update_count} 条记录")
    
    # 验证结果
    print("\n📊 验证数据...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN volume_ratio IS NOT NULL THEN 1 ELSE 0 END) as vol_ratio_count,
                SUM(CASE WHEN net_mf_amount IS NOT NULL THEN 1 ELSE 0 END) as net_mf_count,
                SUM(CASE WHEN pe_ttm IS NOT NULL THEN 1 ELSE 0 END) as pe_ttm_count,
                SUM(CASE WHEN ps IS NOT NULL THEN 1 ELSE 0 END) as ps_count,
                SUM(CASE WHEN break_high_20 IS NOT NULL THEN 1 ELSE 0 END) as high_20_count,
                SUM(CASE WHEN consec_up_days IS NOT NULL THEN 1 ELSE 0 END) as consec_count
            FROM stock_daily_snapshot 
            WHERE trade_date = '2026-06-01'
        """))
        row = result.mappings().first()
        
        print(f"总记录数: {row['total']}")
        print(f"量比非空: {row['vol_ratio_count']}")
        print(f"净流入非空: {row['net_mf_count']}")
        print(f"PE-TTM非空: {row['pe_ttm_count']}")
        print(f"PS非空: {row['ps_count']}")
        print(f"20日新高非空: {row['high_20_count']}")
        print(f"连涨天非空: {row['consec_count']}")

if __name__ == '__main__':
    main()
