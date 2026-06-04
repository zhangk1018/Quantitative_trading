#!/usr/bin/env python3
"""
更新股票基本信息表 - 从数据库 stock_list 读取数据

重要说明：
- 数据源：数据库 stock_list 表（而非 parquet 文件）
- 目标表：stock_basic
- 确保 stock_list 表已有数据（先运行 update_stock_list.py）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pandas as pd
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config


def read_from_database_stock_list(storage):
    """从数据库 stock_list 表读取数据"""
    cursor = storage.conn.cursor()

    cursor.execute('''
        SELECT ts_code, name, list_date, out_date, type, status,
               market, market_name, code, industry
        FROM stock_list
        ORDER BY ts_code
    ''')

    rows = cursor.fetchall()

    if not rows:
        cursor.close()
        return None

    columns = ['ts_code', 'name', 'list_date', 'out_date', 'type', 'status',
               'market', 'market_name', 'code', 'industry']

    df = pd.DataFrame(rows, columns=columns)
    cursor.close()

    return df


def convert_code(ts_code, market):
    """转换代码格式"""
    code_num = ts_code.split('.')[0]
    if market == 'sh_main':
        return f'sh.{code_num}'
    else:
        return f'SZ.{code_num}'


def main():
    print('=' * 60)
    print('          更新股票基本信息表')
    print('=' * 60)
    print()

    config = load_config()
    storage_config = config.get('storage', {}).get('postgresql', {})
    storage = PostgreSQLStorage(storage_config)
    storage.connect()

    print('📥 从数据库 stock_list 表读取数据...')
    df = read_from_database_stock_list(storage)

    if df is None or len(df) == 0:
        print('❌ stock_list 表中没有数据')
        print('💡 请先运行 update_stock_list.py 获取数据')
        storage.disconnect()
        sys.exit(1)

    print(f'✅ 读取到 {len(df)} 条数据')

    df_filtered = df[df['market'].isin(['sh_main', 'sz_main', 'gem'])].copy()
    print(f'📊 过滤后剩余 {len(df_filtered)} 条（排除科创板等）')

    df_filtered['code'] = df_filtered.apply(
        lambda x: convert_code(x['ts_code'], x['market']), axis=1
    )

    df_filtered['exchange'] = df_filtered['market'].map({
        'sh_main': 'SH',
        'sz_main': 'SZ',
        'gem': 'SZ'
    })

    if 'industry' not in df_filtered.columns:
        df_filtered['industry'] = None
    if 'list_date' not in df_filtered.columns:
        df_filtered['list_date'] = None
    if 'delist_date' not in df_filtered.columns:
        df_filtered['delist_date'] = None

    print(f'\n数据预览:')
    print(df_filtered[['ts_code', 'name', 'exchange', 'industry', 'list_date']].head(10))

    print(f'\n市场分布:')
    print(df_filtered['market_name'].value_counts())

    print(f'\n行业分布:')
    print(df_filtered['industry'].value_counts().head(10))

    cursor = storage.conn.cursor()

    print('\n🗑️ 清空现有 stock_basic 数据...')
    cursor.execute('DELETE FROM stock_basic')
    storage.conn.commit()

    print('📥 开始导入...')
    success_count = 0
    fail_count = 0

    for idx, row in df_filtered.iterrows():
        try:
            industry_val = None if pd.isna(row.get('industry', None)) or row.get('industry', None) == '' else row['industry']
            list_date_val = row.get('list_date', None)
            delist_date_val = None

            cursor.execute('''
                INSERT INTO stock_basic (code, name, exchange, industry, list_date, delist_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    exchange = EXCLUDED.exchange,
                    industry = EXCLUDED.industry,
                    list_date = EXCLUDED.list_date,
                    delist_date = EXCLUDED.delist_date
            ''', (row['code'], row['name'], row['exchange'], industry_val, list_date_val, delist_date_val))
            success_count += 1
            if success_count % 500 == 0:
                storage.conn.commit()
                print(f'  已提交 {success_count} 条...')
        except Exception as e:
            fail_count += 1
            if fail_count <= 5:
                print(f'  插入失败 {row["code"]}: {e}')

    storage.conn.commit()

    cursor.execute('SELECT COUNT(*) FROM stock_basic')
    total = cursor.fetchone()[0]
    print(f'\n✅ 导入完成！成功 {success_count}，失败 {fail_count}，数据库中现有 {total} 只股票')

    cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE code LIKE 'sh.6%'")
    sh = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE code LIKE 'SZ.000%'")
    sz000 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE code LIKE 'SZ.300%'")
    sz300 = cursor.fetchone()[0]
    print(f'  上海主板(60): {sh}')
    print(f'  深圳主板(000): {sz000}')
    print(f'  创业板(300): {sz300}')

    cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE industry IS NOT NULL AND industry != ''")
    industry_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE list_date IS NOT NULL")
    list_date_count = cursor.fetchone()[0]
    print(f'\n📊 数据完整性验证:')
    print(f'  industry 非空: {industry_count}')
    print(f'  list_date 非空: {list_date_count}')

    cursor.close()
    storage.disconnect()

    print('\n🎉 stock_basic 表更新完成！')


if __name__ == '__main__':
    main()
