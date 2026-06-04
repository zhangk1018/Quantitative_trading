#!/usr/bin/env python3
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config

config = load_config()
storage_config = config.get('storage', {}).get('postgresql', {})
storage = PostgreSQLStorage(storage_config)
storage.connect()

result = storage.execute_query("""
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'stock_quotes'
ORDER BY ordinal_position
""")

print("=== stock_quotes 表结构 ===")
for row in result:
    print(f"  {row[0]}: {row[1]}")

result = storage.execute_query("""
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'stock_basic'
ORDER BY ordinal_position
""")

print("\n=== stock_basic 表结构 ===")
for row in result:
    print(f"  {row[0]}: {row[1]}")

storage.disconnect()
