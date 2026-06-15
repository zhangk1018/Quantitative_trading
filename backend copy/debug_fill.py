#!/usr/bin/env python3
"""调试程序"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

print("Python path:", sys.path[:3])

# 测试导入
try:
    from utils.logger import setup_logger
    print("✅ setup_logger 导入成功")
except Exception as e:
    print("❌ setup_logger 导入失败:", e)
    import traceback
    traceback.print_exc()

try:
    from collector.storage.postgresql_storage import PostgreSQLStorage
    print("✅ PostgreSQLStorage 导入成功")
except Exception as e:
    print("❌ PostgreSQLStorage 导入失败:", e)
    import traceback
    traceback.print_exc()

try:
    from utils.config import config
    print("✅ config 导入成功")
except Exception as e:
    print("❌ config 导入失败:", e)
    import traceback
    traceback.print_exc()

# 测试 get_missing_stocks
try:
    print("Connecting to database...")
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    storage.connect()
    print("✅ 数据库连接成功")
    
    # 测试查询
    cursor = storage.conn.cursor()
    
    # 查询股票数
    cursor.execute("SELECT COUNT(*) FROM stock_basic")
    print("Stock basic count:", cursor.fetchone()[0])
    
    # 查询2026年数据
    cursor.execute("""
        SELECT COUNT(DISTINCT code), MIN(trade_date), MAX(trade_date) 
        FROM stock_quotes 
        WHERE cycle='1d' AND trade_date >= '2026-01-01' AND trade_date <= '2026-05-31'
    """)
    count, min_date, max_date = cursor.fetchone()
    print("2026年1-5月有数据的股票数:", count)
    print("2026年数据范围:", min_date, "到", max_date)
    
    # 查找缺失的股票
    cursor.execute("""
        SELECT COUNT(sb.code)
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
    """)
    missing_count = cursor.fetchone()[0]
    print("2026年数据少于40天的股票数:", missing_count)
    
    cursor.close()
    storage.disconnect()
    print("✅ 测试完成")
    
except Exception as e:
    print("❌ 失败:", e)
    import traceback
    traceback.print_exc()
