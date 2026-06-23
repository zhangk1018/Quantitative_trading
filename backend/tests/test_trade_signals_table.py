#!/usr/bin/env python3
"""测试 trade_signals 表创建"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

print("=" * 60)
print("测试 NEW-B-1: trade_signals 表创建")
print("=" * 60)

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

storage.init_tables()
print("✅ 表结构初始化完成")

# 检查 trade_signals 表是否存在
import psycopg2
cursor = storage.conn.cursor()
cursor.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'trade_signals'
    )
""")
exists = cursor.fetchone()[0]
cursor.close()

if exists:
    print("✅ trade_signals 表已创建")
else:
    print("❌ trade_signals 表未创建")

# 测试插入一条信号数据
import pandas as pd
test_signal = pd.DataFrame([{
    'code': '000001',
    'trade_date': '2026-06-05',
    'signal_type': 'macd_cross',
    'signal_direction': 'buy',
    'signal_value': 0.1234,
    'signal_strength': 80.5,
    'trigger_price': 10.98,
    'trigger_volume': 100000000
}])

count = storage.save_trade_signals(test_signal)
print(f"✅ 测试插入信号: {count} 条")

# 查询信号数据
signals = storage.get_trade_signals(code='000001', limit=10)
print(f"✅ 查询信号数据: {len(signals)} 条")
if not signals.empty:
    print(f"✅ 信号类型: {signals.iloc[0]['signal_type']}")
    print(f"✅ 信号方向: {signals.iloc[0]['signal_direction']}")

storage.disconnect()
print("=" * 60)
print("✅ NEW-B-1 测试完成")
print("=" * 60)