#!/usr/bin/env python3
"""验证数据库中的股票数据"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/src')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config

def main():
    config = load_config()
    storage_config = config.get('storage', {}).get('postgresql', {})
    storage = PostgreSQLStorage(storage_config)
    storage.connect()

    cursor = storage.conn.cursor()

    print('=' * 60)
    print('          数据验证报告')
    print('=' * 60)
    print()

    # 1. 检查 stock_list 表
    cursor.execute('SELECT COUNT(*) FROM stock_list')
    stock_list_count = cursor.fetchone()[0]
    print(f'📊 stock_list 表: {stock_list_count} 条')

    # 2. 检查 stock_basic 表
    cursor.execute('SELECT COUNT(*) FROM stock_basic')
    stock_basic_count = cursor.fetchone()[0]
    print(f'📊 stock_basic 表: {stock_basic_count} 条')

    # 3. 检查两个表的数据一致性
    cursor.execute('''
        SELECT COUNT(SUBSTRING(sl.code, 1, 3))
        FROM stock_list sl
        WHERE sl.market IN ('sh_main', 'sz_main', 'gem')
    ''')
    filtered_stock_list = cursor.fetchone()[0]
    print(f'📊 stock_list 过滤后(沪深主板+创业板): {filtered_stock_list} 条')

    print()
    print('=== stock_basic 表数据示例 ===')
    cursor.execute('SELECT code, name, exchange, industry, list_date FROM stock_basic LIMIT 5')
    for row in cursor.fetchall():
        industry = row[3] if row[3] else '空'
        list_date = row[4] if row[4] else '空'
        print(f'  {row[0]} | {row[1]} | {row[2]} | {industry} | {list_date}')

    print()
    print('=== 市场分布统计 ===')

    cursor.execute('''
        SELECT
            CASE
                WHEN code LIKE 'sh.%' THEN '上海主板'
                WHEN code LIKE 'SZ.000%' THEN '深圳主板(000)'
                WHEN code LIKE 'SZ.001%' THEN '深圳主板(001)'
                WHEN code LIKE 'SZ.002%' THEN '深圳主板(002)'
                WHEN code LIKE 'SZ.300%' THEN '创业板(300)'
                WHEN code LIKE 'SZ.301%' THEN '创业板(301)'
                ELSE '其他'
            END as market_type,
            COUNT(*) as cnt
        FROM stock_basic
        GROUP BY market_type
        ORDER BY market_type
    ''')

    for row in cursor.fetchall():
        print(f'  {row[0]}: {row[1]}')

    print()
    print('=== 行业分布 (Top 10) ===')
    cursor.execute('''
        SELECT COALESCE(industry, '未知') as industry, COUNT(*) as cnt
        FROM stock_basic
        GROUP BY industry
        ORDER BY cnt DESC
        LIMIT 10
    ''')

    for row in cursor.fetchall():
        print(f'  {row[0]}: {row[1]}')

    print()
    print('=== 上市日期统计 ===')
    cursor.execute('SELECT COUNT(*) FROM stock_basic WHERE list_date IS NOT NULL')
    with_date = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stock_basic WHERE list_date IS NULL')
    without_date = cursor.fetchone()[0]
    print(f'  有上市日期: {with_date}')
    print(f'  无上市日期: {without_date}')

    cursor.close()
    storage.disconnect()

    print()
    print('=' * 60)
    print('✅ 验证完成')
    print('=' * 60)

if __name__ == '__main__':
    main()
