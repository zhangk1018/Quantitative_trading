#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

storage_config = config.storage.get('postgresql', {})
storage = PostgreSQLStorage(storage_config)
storage.connect()

cursor = storage.conn.cursor()

print("开始清理不合规股票数据...")

# 删除 sh.688 开头的（科创板）
cursor.execute("DELETE FROM stock_basic WHERE code LIKE 'sh.688%%'")
deleted = cursor.rowcount
print(f"删除 sh.688%% 股票: {deleted} 只")

# 删除 sh.9 开头的（沪市B股）
cursor.execute("DELETE FROM stock_basic WHERE code LIKE 'sh.9%%'")
deleted = cursor.rowcount
print(f"删除 sh.9%% (B股): {deleted} 只")

# 删除 SZ.2 开头的（深市B股）
cursor.execute("DELETE FROM stock_basic WHERE code LIKE 'SZ.2%%'")
deleted = cursor.rowcount
print(f"删除 SZ.2%% (B股): {deleted} 只")

# 删除 SZ.8 开头的（北交所）
cursor.execute("DELETE FROM stock_basic WHERE code LIKE 'SZ.8%%'")
deleted = cursor.rowcount
print(f"删除 SZ.8%% (北交所): {deleted} 只")

# 注意：SZ.001xxx 和 SZ.002xxx 是深市主板和中小板股票，应该保留
# 只有当它们已退市时才应该被删除（通过 delist_date 字段判断）

storage.conn.commit()

# 验证
print("\n验证 stock_basic 数据:")
cursor.execute("SELECT COUNT(*) FROM stock_basic")
total = cursor.fetchone()[0]
print(f"  总数: {total}")

cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE code LIKE 'sh.6%%'")
sh6 = cursor.fetchone()[0]
print(f"  上海主板(sh.6%%): {sh6}")

cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE code LIKE 'SZ.000%%'")
sz000 = cursor.fetchone()[0]
print(f"  深圳主板(SZ.000%%): {sz000}")

cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE code LIKE 'SZ.300%%'")
sz300 = cursor.fetchone()[0]
print(f"  创业板(SZ.300%%): {sz300}")

valid = sh6 + sz000 + sz300
print(f"  合规股票总数: {valid}")
print(f"  差异: {total - valid} (应为0)")

print("\n清理完成!")