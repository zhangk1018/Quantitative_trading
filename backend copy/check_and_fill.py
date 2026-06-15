#!/usr/bin/env python3
"""
简单脚本：检查2026年数据状况，并开始补全
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from utils.config import config

db_config = config.get('database', {})

conn = psycopg2.connect(
    host=db_config.get('host', 'localhost'),
    port=db_config.get('port', 5432),
    database=db_config.get('database', 'quant_trading'),
    user=db_config.get('username', 'quant_user'),
    password=db_config.get('password', ''),
)

cursor = conn.cursor()

print("="*60)
print("📊 当前数据状况")
print("="*60)

# 查询有多少只股票有2026年数据
cursor.execute("""
    SELECT COUNT(DISTINCT code) 
    FROM stock_quotes 
    WHERE cycle='1d' AND trade_date >= '2026-01-01' AND trade_date <= '2026-05-31'
""")
stocks_with_2026 = cursor.fetchone()[0]

# 查询总股票数
cursor.execute("SELECT COUNT(*) FROM stock_basic")
total_stocks = cursor.fetchone()[0]

cursor.execute("""
    WITH stock_dates AS (
        SELECT 
            sb.code,
            COUNT(DISTINCT sq.trade_date) AS data_days_2026
        FROM stock_basic sb
        LEFT JOIN stock_quotes sq ON sb.code = sq.code 
            AND sq.cycle = '1d' 
            AND sq.trade_date >= '2026-01-01' 
            AND sq.trade_date <= '2026-05-31'
        GROUP BY sb.code
    )
    SELECT COUNT(*) 
    FROM stock_dates 
    WHERE data_days_2026 < 40
""")
missing_2026 = cursor.fetchone()[0]

cursor.execute("""
    SELECT MIN(trade_date), MAX(trade_date) 
    FROM stock_quotes 
    WHERE cycle='1d'
""")
min_date, max_date = cursor.fetchone()

print(f"总股票数: {total_stocks}")
print(f"有2026年1-5月数据的股票数: {stocks_with_2026}")
print(f"2026年数据少于40天的股票数: {missing_2026}")
print(f"数据范围: {min_date} 到 {max_date}")
print(f"覆盖率: {stocks_with_2026/total_stocks*100:.2f}%")

cursor.close()
conn.close()
