#!/usr/bin/env python3
"""检查股票报价数据"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/src')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config

def main():
    config = load_config()
    storage_config = config.get('storage', {}).get('postgresql', {})
    
    storage = PostgreSQLStorage(storage_config)
    storage.connect()
    
    # 使用 cursor 执行查询
    cursor = storage.conn.cursor()
    
    # 检查 stock_quotes 表结构
    cursor.execute('''
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'stock_quotes'
        ORDER BY ordinal_position
    ''')
    result = cursor.fetchall()
    print('stock_quotes 表结构:')
    for row in result:
        print(f'  {row[0]}: {row[1]}')
    
    # 检查是否有 pre_close 字段
    has_pre_close = any(row[0] == 'pre_close' for row in result)
    print(f'\n是否有 pre_close 字段: {has_pre_close}')
    
    # 查询前10条报价数据
    cursor.execute('''
        SELECT code, trade_date, open, close, high, low, volume 
        FROM stock_quotes 
        ORDER BY code, trade_date 
        LIMIT 10
    ''')
    result = cursor.fetchall()
    print('\n前10条报价数据:')
    for row in result:
        print(f'  {row[0]} | {row[1]} | 开盘:{row[2]} | 收盘:{row[3]} | 最高:{row[4]} | 最低:{row[5]} | 成交量:{row[6]}')
    
    # 检查是否需要计算昨收
    if not has_pre_close:
        print('\n⚠️  stock_quotes 表没有 pre_close 字段，需要添加')
    
    cursor.close()
    storage.disconnect()

if __name__ == '__main__':
    main()
