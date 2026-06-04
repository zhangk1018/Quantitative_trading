#!/usr/bin/env python3
"""
检查重复数据
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
    print('📊 重复数据检查')
    print('=' * 60)

    # 查看有多少股票有超过1条记录
    cursor.execute('''
        SELECT code, COUNT(*) as cnt 
        FROM stock_quotes 
        WHERE trade_date = %s 
        GROUP BY code 
        HAVING COUNT(*) > 1 
        ORDER BY cnt DESC 
        LIMIT 10
    ''', ('2026-06-01',))
    results = cursor.fetchall()
    
    print('\n📋 有多条记录的股票（前10）:')
    for code, cnt in results:
        print(f'  {code}: {cnt}条记录')
        
        # 查看这只股票的具体记录
        cursor.execute('SELECT * FROM stock_quotes WHERE code = %s AND trade_date = %s', (code, '2026-06-01'))
        records = cursor.fetchall()
        print(f'    记录详情:')
        for rec in records:
            print(f'      {rec}')

    # 统计有多少股票有多条记录
    cursor.execute('''
        SELECT COUNT(*) 
        FROM (
            SELECT code 
            FROM stock_quotes 
            WHERE trade_date = %s 
            GROUP BY code 
            HAVING COUNT(*) > 1
        ) t
    ''', ('2026-06-01',))
    duplicate_stocks = cursor.fetchone()[0]
    print(f'\n📈 有多条记录的股票总数: {duplicate_stocks}')

    cursor.close()
    storage.disconnect()

if __name__ == '__main__':
    main()
