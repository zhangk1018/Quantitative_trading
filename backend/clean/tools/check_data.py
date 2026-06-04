#!/usr/bin/env python3
"""
检查数据导入情况
"""
import sys
sys.path.insert(0, '.')

from utils.config import config
from utils.storage_factory import StorageFactory

def main():
    storage = StorageFactory.create_storage(config.get('storage'))
    storage.connect()

    cursor = storage.conn.cursor()

    print('=' * 60)
    print('📊 数据分布检查')
    print('=' * 60)

    # 查看不同周期的数据
    cursor.execute('SELECT cycle, COUNT(DISTINCT code), COUNT(*) FROM stock_quotes WHERE trade_date = %s GROUP BY cycle', ('2026-06-01',))
    results = cursor.fetchall()
    print('\n📈 按周期统计:')
    for cycle, code_count, total_count in results:
        print(f'  {cycle}: {code_count}只股票, {total_count}条记录')

    # 查看最近导入的股票
    print('\n📋 最近10条导入记录:')
    cursor.execute('SELECT code, trade_date, created_at FROM stock_quotes ORDER BY created_at DESC LIMIT 10')
    results = cursor.fetchall()
    for code, date, created_at in results:
        print(f'  {code} - {date} - {created_at}')

    cursor.close()
    storage.disconnect()

if __name__ == '__main__':
    main()
