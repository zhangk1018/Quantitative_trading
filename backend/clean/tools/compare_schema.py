#!/usr/bin/env python3
"""对比 stock_list.parquet 和 stock_basic 表结构"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/src')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config
import pandas as pd

# 1. 读取 stock_list.parquet 的字段
df_parquet = pd.read_parquet('data/metadata/stock_list.parquet')
print('=== stock_list.parquet 字段 ===')
for col in df_parquet.columns:
    print(f'  {col}: {df_parquet[col].dtype}')

print()

# 2. 查询数据库 stock_basic 表结构
config = load_config()
storage_config = config.get('storage', {}).get('postgresql', {})
storage = PostgreSQLStorage(storage_config)
storage.connect()

cursor = storage.conn.cursor()
cursor.execute('''
    SELECT column_name, data_type, character_maximum_length
    FROM information_schema.columns
    WHERE table_name = 'stock_basic'
    ORDER BY ordinal_position
''')
result = cursor.fetchall()

print('=== stock_basic 表结构 ===')
for row in result:
    length = row[2] if row[2] else 'N/A'
    print(f'  {row[0]}: {row[1]}({length})')

cursor.close()
storage.disconnect()

print()
print('=== 字段对应关系 ===')
print('''
stock_list.parquet     ->  stock_basic 表
─────────────────────────────────────────
ts_code               ->  code (股票代码)
name                  ->  name (股票名称)
list_date             ->  list_date (上市日期)
outDate               ->  delist_date (退市日期)
market                ->  -
market_name           ->  -
code                  ->  -
industry              ->  industry (行业)
─────────────────────────────────────────
注意：parquet 文件中的字段比数据库表多，
      导入时会选择需要的字段写入。
''')
