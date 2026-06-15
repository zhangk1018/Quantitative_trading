#!/usr/bin/env python3
"""简单快速的2026年1-5月数据补全"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import pandas as pd
from datetime import datetime

from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('quick_fill')


def get_missing_stocks(storage):
    """获取2026年1-5月数据少于40天的股票"""
    cursor = storage.conn.cursor()
    
    query = """
        SELECT sb.code
        FROM stock_basic sb
        LEFT JOIN (
            SELECT code, COUNT(DISTINCT trade_date) AS data_days_2026
            FROM stock_quotes
            WHERE cycle = '1d' 
                AND trade_date >= '2026-01-01' 
                AND trade_date <= '2026-05-31'
            GROUP BY code
        ) sq ON sb.code = sq.code
        WHERE sq.data_days_2026 IS NULL OR sq.data_days_2026 < 40
        ORDER BY sb.code
    """
    cursor.execute(query)
    codes = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return codes


def import_stock(storage, code):
    """导入单只股票2026年1-5月数据"""
    full_code = code
    if '.' in code:
        code6 = code.split('.')[0]
    else:
        code6 = code
    
    try:
        cursor = storage.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT trade_date 
            FROM stock_quotes 
            WHERE code = %s AND cycle = '1d'
                AND trade_date >= '2026-01-01' AND trade_date <= '2026-05-31'
        """, (code6,))
        existing_dates = {row[0] for row in cursor.fetchall()}
        cursor.close()
        
        ds = BaostockDataSource()
        ds.connect()
        df = ds.get_kline(code=code6, cycle='daily', 
                         start_date='2026-01-01', 
                         end_date='2026-05-31')
        ds.disconnect()
        
        if df is None or df.empty:
            logger.warning(f"{code}: Baostock无数据")
            return 0
        
        numeric_cols = ['open', 'high', 'low', 'close', 'amount']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        df['volume'] = df['volume'].where(
            df['volume'].notna() & df['volume'].notnull(), 
            None
        )
        
        price_cols = ['open', 'high', 'low', 'close']
        mask = (df[price_cols] > 0).all(axis=1) & df['volume'].notna() & (df['volume'] > 0)
        df = df[mask]
        
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        new_data_mask = ~df['trade_date'].isin(existing_dates)
        df_new = df[new_data_mask].copy()
        
        if df_new.empty:
            return 0
        
        logger.info(f"{code}: 发现{len(df_new)}条新数据")
        
        df_new['code'] = code6
        df_new['cycle'] = '1d'
        df_new['adjust_type'] = 'qfq'
        
        import_count = 0
        cursor = storage.conn.cursor()
        for _, row in df_new.iterrows():
            trade_datetime = pd.to_datetime(row['trade_date']) + pd.Timedelta('15:00:00')
            params = (
                row['code'],
                row['cycle'],
                row['trade_date'],
                float(row['open']) if pd.notna(row['open']) else 0.0,
                float(row['high']) if pd.notna(row['high']) else 0.0,
                float(row['low']) if pd.notna(row['low']) else 0.0,
                float(row['close']) if pd.notna(row['close']) else 0.0,
                float(row.get('pre_close', 0)) if pd.notna(row.get('pre_close', 0)) else 0.0,
                int(row['volume']) if pd.notna(row['volume']) else 0,
                float(row['amount']) if pd.notna(row['amount']) else 0.0,
                row['adjust_type'],
                trade_datetime
            )
            
            cursor.execute("""
                INSERT INTO stock_quotes (
                    code, cycle, trade_date, open, high, low, close,
                    pre_close, volume, amount, adjust_type, trade_datetime
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code, cycle, trade_date, trade_datetime) DO NOTHING
            """, params)
            if cursor.rowcount > 0:
                import_count += 1
        
        storage.conn.commit()
        cursor.close()
        return import_count
        
    except Exception as e:
        logger.error(f"{code}: 导入失败 {e}")
        return 0


def main():
    print("="*60)
    print("📊 2026年1-5月数据补全")
    print("="*60)
    
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    storage.connect()
    
    codes = get_missing_stocks(storage)
    logger.info(f"发现 {len(codes)} 只股票需要补全")
    
    if len(codes) == 0:
        logger.info("✅ 所有数据都完整")
        storage.disconnect()
        return
    
    success = 0
    fail = 0
    total_records = 0
    
    # 只补全前200只，避免太长时间
    for i, code in enumerate(codes[:200]):
        if (i+1) % 10 == 1:
            logger.info(f"进度: {i+1}/{min(len(codes),200)}")
        
        count = import_stock(storage, code)
        if count > 0:
            success += 1
            total_records += count
        
        if i % 10 == 9:
            time.sleep(0.3)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"完成: 成功{success}只, 导入{total_records}条记录")
    logger.info(f"{'='*60}")
    
    storage.disconnect()


if __name__ == '__main__':
    main()
