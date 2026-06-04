#!/usr/bin/env python3
"""清理测试数据"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

storage = PostgreSQLStorage(config.storage.get('postgresql', {}))
storage.connect()
cursor = storage.conn.cursor()

# 删除测试数据
cursor.execute("""
    DELETE FROM stock_quotes 
    WHERE code = '000001' 
    AND cycle = '1d' 
    AND trade_date BETWEEN '2026-05-06' AND '2026-05-08'
""")
storage.conn.commit()
print(f'✅ 已删除 3 条测试数据')

# 检查5月份数据
cursor.execute("""
    SELECT COUNT(DISTINCT code) 
    FROM stock_quotes 
    WHERE cycle = '1d' 
    AND trade_date BETWEEN '2026-05-01' AND '2026-05-31'
""")
may_count = cursor.fetchone()[0]
print(f'5月份数据覆盖: {may_count} 只股票')

storage.disconnect()
