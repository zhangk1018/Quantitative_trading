#!/usr/bin/env python3
"""每日数据管道晨检 (临时脚本)"""
import os
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

storage = PostgreSQLStorage(config.storage.get('postgresql', {}))
storage.connect()
cur = storage.conn.cursor()

print("=" * 60)
print("1. stock_quotes 最近3个交易日数据量")
print("=" * 60)
cur.execute("""
SELECT trade_date, COUNT(*)
FROM stock_quotes
WHERE cycle='1d' AND trade_date >= CURRENT_DATE - INTERVAL '3 days'
GROUP BY trade_date
ORDER BY trade_date DESC;
""")
for row in cur.fetchall():
    print(f"  trade_date={row[0]}, count={row[1]}")

print()
print("=" * 60)
print("2. stock_daily_snapshot 最近3个交易日数据量")
print("=" * 60)
cur.execute("""
SELECT trade_date, COUNT(*)
FROM stock_daily_snapshot
WHERE trade_date >= CURRENT_DATE - INTERVAL '3 days'
GROUP BY trade_date
ORDER BY trade_date DESC;
""")
for row in cur.fetchall():
    print(f"  trade_date={row[0]}, count={row[1]}")

print()
print("=" * 60)
print("3. 去重股票数 + 最新交易日未更新数")
print("=" * 60)
cur.execute("SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle='1d';")
total_distinct = cur.fetchone()[0]
print(f"  去重股票总数: {total_distinct}")

cur.execute("""
SELECT trade_date FROM stock_quotes
WHERE cycle='1d'
GROUP BY trade_date ORDER BY trade_date DESC LIMIT 1;
""")
latest = cur.fetchone()[0]
print(f"  最新交易日: {latest}")

cur.execute(f"""
SELECT COUNT(*) FROM (
  SELECT DISTINCT code FROM stock_quotes WHERE cycle='1d'
  EXCEPT
  SELECT code FROM stock_quotes WHERE cycle='1d' AND trade_date='{latest}'
) t;
""")
missing = cur.fetchone()[0]
print(f"  最新交易日未更新的股票数: {missing}")

print()
print("=" * 60)
print(f"4. 字段补全率 (trade_date={latest})")
print("=" * 60)
cur.execute(f"""
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN pe IS NOT NULL THEN 1 ELSE 0 END) as pe_count,
    SUM(CASE WHEN ma5 IS NOT NULL THEN 1 ELSE 0 END) as ma5_count,
    SUM(CASE WHEN macd IS NOT NULL THEN 1 ELSE 0 END) as macd_count,
    SUM(CASE WHEN rsi_6 IS NOT NULL THEN 1 ELSE 0 END) as rsi6_count,
    SUM(CASE WHEN boll_mid IS NOT NULL THEN 1 ELSE 0 END) as boll_count
FROM stock_daily_snapshot
WHERE trade_date = '{latest}';
""")
row = cur.fetchone()
total = row[0]
print(f"  total: {total}")
for name, val in zip(["pe", "ma5", "macd", "rsi_6", "boll_mid"], row[1:]):
    rate = (val/total*100) if total else 0
    print(f"  {name}: {val}/{total} = {rate:.1f}%")

print()
print("=" * 60)
print("5. 今日 (2026-06-05) 写入状态")
print("=" * 60)
cur.execute("SELECT trade_date, COUNT(*) FROM stock_quotes WHERE cycle='1d' AND trade_date='2026-06-05' GROUP BY trade_date;")
today_data = cur.fetchall()
print(f"  stock_quotes 2026-06-05: {today_data}")

cur.execute("SELECT trade_date, COUNT(*) FROM stock_daily_snapshot WHERE trade_date='2026-06-05' GROUP BY trade_date;")
today_snap = cur.fetchall()
print(f"  stock_daily_snapshot 2026-06-05: {today_snap}")

cur.close()
storage.disconnect()
