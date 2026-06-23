#!/usr/bin/env python3
"""只测试 PostgreSQLStorage 的简单脚本"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 先测试基本的 PostgreSQL 连接和查询
try:
    import psycopg2
    import pandas as pd
except ImportError as e:
    print(f"缺少必要库: {e}")
    print("请安装: pip install psycopg2-binary pandas")
    sys.exit(1)

from utils.config import config
from collector.storage.postgresql_storage import PostgreSQLStorage


print("=" * 60)
print("测试 PostgreSQLStorage 真实数据读取")
print("=" * 60)

# 初始化 storage
db_config = config.get('database', {})
storage = PostgreSQLStorage({
    'host': db_config.get('host', 'localhost'),
    'port': db_config.get('port', 5432),
    'database': db_config.get('database', 'quant_trading'),
    'username': db_config.get('username', 'quant_user'),
    'password': db_config.get('password', ''),
})

if not storage.connect():
    print("❌ 数据库连接失败")
    sys.exit(1)

print("✅ PostgreSQL 连接成功")

# 1. 测试获取股票列表
print()
print("1. 测试获取股票列表:")
df_all = storage.get_quotes(None, 'daily', limit=100)
if df_all.empty:
    print("  ⚠️ 没有查询到数据")
else:
    codes = df_all['code'].unique()
    print(f"  ✅ 查询到 {len(df_all)} 条记录，{len(codes)} 只股票")
    print(f"  ✅ 示例股票: {codes[:5]}")

# 2. 测试获取单只股票数据
print()
print("2. 测试获取单只股票数据 (000001):")
df_single = storage.get_quotes('000001', 'daily')
if df_single.empty:
    print("  ⚠️ 000001 没有数据")
else:
    print(f"  ✅ 000001 查询到 {len(df_single)} 条记录")
    df_sorted = df_single.sort_values('trade_date', ascending=False)
    print(f"  ✅ 最新日期: {df_sorted.iloc[0]['trade_date']}")
    print(f"  ✅ 最新收盘价: {df_sorted.iloc[0]['close']}")

# 3. 初始化表结构（确保 trade_signals 存在）
print()
print("3. 初始化表结构:")
try:
    storage.init_tables()
    print("  ✅ 表结构初始化成功")
except Exception as e:
    print(f"  ❌ 表初始化失败: {e}")

# 4. 测试信号查询
print()
print("4. 查询现有信号:")
signals_df = storage.get_signals()
print(f"  trade_signals 表现有 {len(signals_df)} 条记录")

storage.disconnect()

print()
print("=" * 60)
print("✅ 基础存储测试完成")
print("=" * 60)
