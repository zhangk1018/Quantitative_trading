#!/usr/bin/env python3
"""导出数据库数据到Parquet文件（包含14个技术指标pattern列）"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
from sqlalchemy import create_engine, text
from utils.config import load_config

def export_to_parquet():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)
    
    output_path = 'data/price/daily/latest_quotes.parquet'
    
    print("📤 导出数据到Parquet...")
    
    with engine.connect() as conn:
        # 获取最新交易日期
        result = conn.execute(text("""
            SELECT MAX(trade_date) as latest_date 
            FROM stock_daily_snapshot
        """))
        latest_date = result.fetchone()[0]
        print(f"📅 导出日期: {latest_date}")
        
        # 导出数据
        result = conn.execute(text(f"""
            SELECT * FROM stock_daily_snapshot 
            WHERE trade_date = '{latest_date}'
        """))
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        # 转换日期格式为YYYYMMDD
        df['trade_date'] = df['trade_date'].apply(lambda x: x.strftime('%Y%m%d') if x else '')
        
        # 保存
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_parquet(output_path, index=False)
    
    print(f"✅ 导出完成: {output_path}")
    print(f"📊 导出记录数: {len(df)}")
    print(f"📋 列数: {len(df.columns)}")
    
    # 验证pattern列
    pattern_cols = [c for c in df.columns if any(x in c for x in ['ma_long', 'ma_short', 'macd_low', 'macd_high', 'boll_break', 'rsi_low', 'rsi_high'])]
    print(f"🔍 Pattern列数: {len(pattern_cols)}")
    for col in sorted(pattern_cols):
        count = df[col].sum() if df[col].dtype in ['int64', 'bool'] else 0
        print(f"  - {col}: {count}")

if __name__ == '__main__':
    export_to_parquet()
