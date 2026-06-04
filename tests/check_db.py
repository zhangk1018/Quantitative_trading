#!/usr/bin/env python3
"""检查数据库状态"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

storage = PostgreSQLStorage(config.storage.get('postgresql', {}))
storage.connect()
cursor = storage.conn.cursor()

# 今日数据
cursor.execute("SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle = '1d' AND trade_date = '2026-06-03'")
today_count = cursor.fetchone()[0]
print(f'今日(2026-06-03)数据: {today_count} 只股票')

# 数据库总数据
cursor.execute("SELECT COUNT(*) FROM stock_quotes WHERE cycle = '1d'")
total = cursor.fetchone()[0]
print(f'数据库总数据: {total} 条')

# 最新数据日期
cursor.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
max_date = cursor.fetchone()[0]
print(f'最新数据日期: {max_date}')

# 按日期统计
cursor.execute("""
    SELECT trade_date, COUNT(DISTINCT code) as cnt
    FROM stock_quotes
    WHERE cycle = '1d'
    GROUP BY trade_date
    ORDER BY trade_date DESC
    LIMIT 5
""")
dates = cursor.fetchall()
print('\n最近5个交易日:')
for d in dates:
    print(f'  {d[0]}: {d[1]} 只股票')

storage.disconnect()
