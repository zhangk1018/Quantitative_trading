#!/usr/bin/env python3
"""检查 stock_basic 表的数据"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/src')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config

config = load_config()
storage_config = config.get('storage', {}).get('postgresql', {})
storage = PostgreSQLStorage(storage_config)
storage.connect()

cursor = storage.conn.cursor()

print('=== stock_basic 表数据检查 ===\n')

# 总数
cursor.execute('SELECT COUNT(*) FROM stock_basic')
print(f'总记录数: {cursor.fetchone()[0]}')

# 按前缀统计
cursor.execute("SELECT SUBSTRING(code, 1, 2) AS prefix, COUNT(*) FROM stock_basic GROUP BY prefix ORDER BY prefix")
print('\n按前缀统计:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}')

# 检查 sh.6% 的记录
cursor.execute("SELECT code FROM stock_basic WHERE code LIKE 'sh.6%' LIMIT 5")
print('\nsh.6 开头的代码示例:')
for row in cursor.fetchall():
    print(f'  {row[0]}')

# 检查 SZ.000% 的记录
cursor.execute("SELECT code FROM stock_basic WHERE code LIKE 'SZ.000%' LIMIT 5")
print('\nSZ.000 开头的代码示例:')
for row in cursor.fetchall():
    print(f'  {row[0]}')

# 检查 SZ.300% 的记录
cursor.execute("SELECT code FROM stock_basic WHERE code LIKE 'SZ.300%' LIMIT 5")
print('\nSZ.300 开头的代码示例:')
for row in cursor.fetchall():
    print(f'  {row[0]}')

# 检查其他 SZ.% 的记录
cursor.execute("SELECT code FROM stock_basic WHERE code LIKE 'SZ.%' AND code NOT LIKE 'SZ.000%' AND code NOT LIKE 'SZ.300%' LIMIT 10")
print('\n其他 SZ.% 的代码示例:')
for row in cursor.fetchall():
    print(f'  {row[0]}')

cursor.close()
storage.disconnect()
