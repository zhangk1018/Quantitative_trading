#!/usr/bin/env python3
"""
数据补全和清洗主程序

执行流程：
1. 从Parquet文件同步基础数据到数据库
2. 计算技术指标（MA5, MA10, MA20, 5日均量）
3. 更新数据库宽表
4. 导出更新后的数据到Parquet文件

触发条件：股市收盘数据完成后自动执行
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
from sqlalchemy import create_engine, text
from utils.config import load_config

def sync_parquet_to_db(engine, parquet_path: str, trade_date: str):
    """从Parquet文件同步数据到数据库"""
    print(f"📥 读取Parquet文件: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    print(f"✅ 文件包含 {len(df)} 条记录")
    
    print("\n🔄 同步数据到数据库...")
    update_count = 0
    
    with engine.connect() as conn:
        for _, row in df.iterrows():
            ts_code = row['ts_code']
            code = ts_code.replace('.SZ', '').replace('.SH', '')
            
            update_fields = []
            params = {'code': code, 'trade_date': trade_date}
            
            # 基本字段
            if pd.notna(row.get('name')):
                update_fields.append('stock_name = :stock_name')
                params['stock_name'] = str(row['name'])
            
            if pd.notna(row.get('industry')):
                update_fields.append('industry = :industry')
                params['industry'] = str(row['industry'])
            
            if pd.notna(row.get('area')):
                update_fields.append('area = :area')
                params['area'] = str(row['area'])
            
            # 价格字段
            if pd.notna(row.get('close')):
                update_fields.append('close = :close')
                params['close'] = round(float(row['close']), 2)
            
            if pd.notna(row.get('open')):
                update_fields.append('open = :open')
                params['open'] = round(float(row['open']), 2)
            
            if pd.notna(row.get('high')):
                update_fields.append('high = :high')
                params['high'] = round(float(row['high']), 2)
            
            if pd.notna(row.get('low')):
                update_fields.append('low = :low')
                params['low'] = round(float(row['low']), 2)
            
            # 资金流向字段
            for field in ['buy_sm_amount', 'sell_sm_amount', 'buy_md_amount', 'sell_md_amount',
                         'buy_lg_amount', 'sell_lg_amount', 'buy_elg_amount', 'sell_elg_amount',
                         'net_mf_amount', 'volume_ratio', 'vol_ratio_5']:
                value = row.get(field)
                if pd.notna(value):
                    update_fields.append(f'{field} = :{field}')
                    params[field] = round(float(value), 2)
            
            # 技术指标（仅更新数据库中已存在的字段）
            for field in ['rsi_6', 'macd', 'boll_upper', 'boll_mid', 'boll_lower']:
                value = row.get(field)
                if pd.notna(value):
                    update_fields.append(f'{field} = :{field}')
                    params[field] = round(float(value), 2)
            
            if update_fields:
                sql = f"""
                    UPDATE stock_daily_snapshot 
                    SET {', '.join(update_fields)}
                    WHERE code = :code AND trade_date = :trade_date
                """
                conn.execute(text(sql), params)
                update_count += 1
        
        conn.commit()
    
    print(f"✅ 同步完成，更新了 {update_count} 条记录")
    return df

def calculate_technical_indicators(engine, trade_date: str):
    """计算并更新技术指标"""
    print(f"\n🔢 计算技术指标 ({trade_date})...")
    
    with engine.connect() as conn:
        # 获取股票列表
        result = conn.execute(text(f"SELECT DISTINCT code FROM stock_daily_snapshot WHERE trade_date = '{trade_date}'"))
        codes = [row[0] for row in result.fetchall()]
        print(f"📊 处理 {len(codes)} 只股票")
        
        count = 0
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
                
                # 计算均线
                ma5 = sum(closes[:5]) / 5 if len(closes) >= 5 else None
                ma10 = sum(closes[:10]) / 10 if len(closes) >= 10 else None
                ma20 = sum(closes[:20]) / 20 if len(closes) >= 20 else None
                v_ma5 = int(sum(volumes[:5]) / 5) if len(volumes) >= 5 else None
                
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
                        WHERE code = :code AND trade_date = '{trade_date}'
                    """
                    conn.execute(text(sql), params)
                    count += 1
        
        conn.commit()
    
    print(f"✅ 技术指标计算完成，更新了 {count} 条记录")

def export_db_to_parquet(engine, trade_date: str, output_path: str):
    """导出数据库数据到Parquet文件"""
    print(f"\n📤 导出数据到Parquet...")
    
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT * FROM stock_daily_snapshot WHERE trade_date = '{trade_date}'
        """))
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        # 转换日期格式为YYYYMMDD
        df['trade_date'] = df['trade_date'].apply(lambda x: x.strftime('%Y%m%d') if x else '')
        
        # 保存
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_parquet(output_path, index=False)
    
    print(f"✅ 导出完成: {output_path}")
    print(f"📊 导出记录数: {len(df)}")

def verify_data(engine, trade_date: str):
    """验证数据完整性"""
    print(f"\n🔍 验证数据 ({trade_date})...")
    
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN ma5 IS NOT NULL THEN 1 ELSE 0 END) as ma5_count,
                SUM(CASE WHEN ma10 IS NOT NULL THEN 1 ELSE 0 END) as ma10_count,
                SUM(CASE WHEN ma20 IS NOT NULL THEN 1 ELSE 0 END) as ma20_count,
                SUM(CASE WHEN v_ma5 IS NOT NULL THEN 1 ELSE 0 END) as v_ma5_count,
                SUM(CASE WHEN buy_sm_amount IS NOT NULL THEN 1 ELSE 0 END) as buy_sm_count
            FROM stock_daily_snapshot 
            WHERE trade_date = '{trade_date}'
        """))
        row = result.mappings().first()
        
        print(f"总记录数: {row['total']}")
        print(f"MA5非空: {row['ma5_count']} ({row['ma5_count']/row['total']*100:.1f}%)")
        print(f"MA10非空: {row['ma10_count']} ({row['ma10_count']/row['total']*100:.1f}%)")
        print(f"MA20非空: {row['ma20_count']} ({row['ma20_count']/row['total']*100:.1f}%)")
        print(f"5日均量非空: {row['v_ma5_count']} ({row['v_ma5_count']/row['total']*100:.1f}%)")
        print(f"资金流向非空: {row['buy_sm_count']} ({row['buy_sm_count']/row['total']*100:.1f}%)")

def main():
    print("============================================")
    print("📦 数据补全和清洗程序")
    print("============================================")
    
    # 加载配置
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)
    
    # 日期配置（从parquet文件读取）
    parquet_path = 'data/price/daily/latest_quotes.parquet'
    df_check = pd.read_parquet(parquet_path)
    trade_date_str = str(df_check['trade_date'].iloc[0])  # YYYYMMDD格式
    trade_date = f"{trade_date_str[:4]}-{trade_date_str[4:6]}-{trade_date_str[6:]}"  # YYYY-MM-DD格式
    
    print(f"\n📅 处理日期: {trade_date}")
    
    try:
        # 步骤1: 从Parquet同步到数据库
        sync_parquet_to_db(engine, parquet_path, trade_date)
        
        # 步骤2: 计算技术指标
        calculate_technical_indicators(engine, trade_date)
        
        # 步骤3: 导出到Parquet
        export_db_to_parquet(engine, trade_date, parquet_path)
        
        # 步骤4: 验证数据
        verify_data(engine, trade_date)
        
        print("\n🎉 数据补全和清洗完成！")
        
    except Exception as e:
        print(f"\n❌ 执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()