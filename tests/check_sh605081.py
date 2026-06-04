#!/usr/bin/env python3
"""查询 sh.605081 股票后10条记录"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

storage = PostgreSQLStorage(config.storage.get('postgresql', {}))
storage.connect()
cursor = storage.conn.cursor()

# 检查这只股票是否有数据
cursor.execute("""
    SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
    FROM stock_quotes
    WHERE code = '605081' AND cycle = '1d'
""")
count, min_date, max_date = cursor.fetchone()
print(f"605081 总记录数: {count}")
if count > 0:
    print(f"日期范围: {min_date} 至 {max_date}")

# 查询 605081 的后10条记录
cursor.execute("""
    SELECT *
    FROM stock_quotes
    WHERE code = '605081' AND cycle = '1d'
    ORDER BY trade_date DESC
    LIMIT 10
""")
rows = cursor.fetchall()

# 获取列名
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'stock_quotes' ORDER BY ordinal_position")
columns = [col[0] for col in cursor.fetchall()]

print(f"\n605081 后10条记录（按时间倒序）：")
print("=" * 120)
print(f"{'交易日期':<12} {'开盘':<8} {'最高':<8} {'最低':<8} {'收盘':<8} {'成交量':<12} {'成交额':<14} {'前收盘':<8}")
print("-" * 120)
for row in rows:
    trade_date = row[3]
    open_price = row[4]
    high = row[5]
    low = row[6]
    close = row[7]
    volume = row[8]
    amount = row[9]
    pre_close = row[12]
    print(f"{trade_date!s:<12} {open_price:<8} {high:<8} {low:<8} {close:<8} {volume:<12} {amount:<14} {pre_close:<8}")
print("=" * 120)

# 如果没有数据，检查数据库总情况
if count == 0:
    print("\n没有找到 sh.605081 的数据。检查数据库总体情况...")
    cursor.execute("""
        SELECT code, COUNT(*) as cnt
        FROM stock_quotes
        WHERE cycle = '1d'
        GROUP BY code
        ORDER BY cnt DESC
        LIMIT 5
    """)
    print("\n有数据的股票（前5个）：")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} 条")

storage.disconnect()
