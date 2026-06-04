#!/usr/bin/env python3
"""更新股票列表 - 从 Baostock 获取全量 A 股列表

更新说明：
- 同时保存到 parquet 文件和数据库 stock_list 表
- 数据库 stock_list 表作为主要数据源
- parquet 文件作为备份缓存
"""
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from utils.logger import setup_logger
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config

logger = setup_logger('update_stock_list')


def fetch_all_a_shares_from_baostock():
    """从 Baostock 获取全量 A 股列表"""
    try:
        import baostock as bs

        print('📡 正在从 Baostock 获取全量 A 股列表...')

        lg = bs.login()
        if lg.error_code != '0':
            print(f'❌ Baostock 登录失败：{lg.error_msg}')
            return None

        rs = bs.query_stock_basic()

        if rs.error_code != '0':
            print(f'❌ 获取股票列表失败：{rs.error_msg}')
            bs.logout()
            return None

        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())

        df = pd.DataFrame(data_list, columns=rs.fields)

        bs.logout()

        if len(df) == 0:
            print('❌ 未获取到数据')
            return None

        print(f'获取到 {len(df)} 条原始数据')
        print(f'字段列表: {rs.fields}')

        df = df[df['code'].str.startswith(('sh.60', 'sh.68', 'sz.000', 'sz.001', 'sz.002', 'sz.300', 'sz.301'))]

        print(f'过滤后剩余 {len(df)} 条 A 股数据')

        df = df.rename(columns={
            'code': 'ts_code',
            'code_name': 'name',
            'ipoDate': 'list_date',
            'outDate': 'out_date',
            'industry': 'industry'
        })

        df['ts_code'] = df['ts_code'].apply(
            lambda x: x.replace('sh.', '') + '.SH' if x.startswith('sh.')
            else x.replace('sz.', '') + '.SZ'
        )

        market_list = []
        market_name_list = []
        for ts_code in df['ts_code']:
            prefix = ts_code[:3]
            if prefix.startswith('68'):
                market_list.append('star')
                market_name_list.append('科创板')
            elif prefix.startswith('60'):
                market_list.append('sh_main')
                market_name_list.append('上海主板')
            elif prefix in ['000', '001', '002']:
                market_list.append('sz_main')
                market_name_list.append('深圳主板')
            elif prefix in ['300', '301']:
                market_list.append('gem')
                market_name_list.append('创业板')
            else:
                market_list.append('other')
                market_name_list.append('其他')

        df['market'] = market_list
        df['market_name'] = market_name_list

        df['code'] = df['ts_code'].str.replace('.SH', '').str.replace('.SZ', '')

        if 'industry' not in df.columns:
            df['industry'] = ''

        if 'out_date' not in df.columns:
            df['out_date'] = ''

        if 'status' not in df.columns:
            df['status'] = '1'

        if 'type' not in df.columns:
            df['type'] = '1'

        print(f'✅ 成功获取 {len(df)} 只股票')
        return df

    except ImportError:
        print('⚠️  Baostock 未安装，尝试使用 Akshare...')
        return fetch_all_a_shares_from_akshare()
    except Exception as e:
        print(f'❌ 获取失败：{e}')
        import traceback
        traceback.print_exc()
        return None


def fetch_all_a_shares_from_akshare():
    """从 Akshare 获取全量 A 股列表"""
    try:
        import akshare as ak

        print('📡 正在从 Akshare 获取全量 A 股列表...')

        df = ak.stock_info_a_code_name()

        print(f'✅ 成功获取 {len(df)} 只股票')

        df = df.rename(columns={
            'code': 'ts_code',
            'name': 'name'
        })

        market_list = []
        market_name_list = []
        for ts_code in df['ts_code']:
            prefix = ts_code[:3]
            if prefix.startswith('68'):
                market_list.append('star')
                market_name_list.append('科创板')
            elif prefix.startswith('60'):
                market_list.append('sh_main')
                market_name_list.append('上海主板')
            elif prefix in ['000', '001', '002']:
                market_list.append('sz_main')
                market_name_list.append('深圳主板')
            elif prefix in ['300', '301']:
                market_list.append('gem')
                market_name_list.append('创业板')
            else:
                market_list.append('other')
                market_name_list.append('其他')

        df['market'] = market_list
        df['market_name'] = market_name_list

        df['industry'] = ''
        df['list_date'] = ''
        df['out_date'] = ''
        df['code'] = df['ts_code']
        df['status'] = '1'
        df['type'] = '1'

        return df

    except Exception as e:
        print(f'❌ Akshare 获取失败：{e}')
        import traceback
        traceback.print_exc()
        return None


def create_stock_list_table(storage):
    """创建 stock_list 表（如果不存在）"""
    cursor = storage.conn.cursor()

    create_table_sql = '''
        CREATE TABLE IF NOT EXISTS stock_list (
            id SERIAL PRIMARY KEY,
            ts_code VARCHAR(15) UNIQUE NOT NULL,
            name VARCHAR(50) NOT NULL,
            list_date DATE,
            out_date DATE,
            type VARCHAR(20),
            status VARCHAR(20),
            market VARCHAR(20),
            market_name VARCHAR(50),
            code VARCHAR(10),
            industry VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    '''

    cursor.execute(create_table_sql)
    storage.conn.commit()
    cursor.close()
    print('✅ stock_list 表已准备好')


def save_to_database(df, storage):
    """保存到数据库 stock_list 表"""
    if df is None or len(df) == 0:
        print('⚠️ 没有数据可保存到数据库')
        return False

    cursor = storage.conn.cursor()

    df['list_date'] = pd.to_datetime(df['list_date'], errors='coerce')
    df['out_date'] = pd.to_datetime(df['out_date'], errors='coerce')

    df['list_date'] = df['list_date'].apply(lambda x: x.date() if pd.notna(x) else None)
    df['out_date'] = df['out_date'].apply(lambda x: x.date() if pd.notna(x) else None)

    df = df.replace({'': None})

    from io import StringIO

    output = StringIO()
    for _, row in df.iterrows():
        line = '\t'.join([
            str(row['ts_code']),
            str(row['name']),
            str(row['list_date']) if row['list_date'] else '',
            str(row['out_date']) if row['out_date'] else '',
            str(row.get('type', '')) if row.get('type') else '',
            str(row.get('status', '')) if row.get('status') else '',
            str(row.get('market', '')) if row.get('market') else '',
            str(row.get('market_name', '')) if row.get('market_name') else '',
            str(row.get('code', '')) if row.get('code') else '',
            str(row.get('industry', '')) if row.get('industry') else ''
        ])
        output.write(line + '\n')

    output.seek(0)

    try:
        cursor.copy_from(
            file=output,
            table='stock_list',
            columns=('ts_code', 'name', 'list_date', 'out_date', 'type', 'status',
                    'market', 'market_name', 'code', 'industry'),
            null=''
        )
        storage.conn.commit()
        print(f'✅ 批量导入数据库成功：{len(df)} 条')
        return True
    except Exception as e:
        storage.conn.rollback()
        print(f'❌ 批量导入失败：{e}')
        return False
    finally:
        cursor.close()


def save_to_parquet(df):
    """保存到 parquet 文件（作为备份）"""
    if df is None or len(df) == 0:
        print('⚠️ 没有数据可保存到文件')
        return False

    os.makedirs('data/metadata', exist_ok=True)
    output_path = 'data/metadata/stock_list.parquet'
    df.to_parquet(output_path, index=False)

    print(f'✅ 已备份到 {output_path}')
    return True


def main():
    print('=' * 60)
    print('          更新股票列表')
    print('=' * 60)

    df = fetch_all_a_shares_from_baostock()

    if df is None or len(df) == 0:
        print('❌ 无法获取股票列表，程序退出')
        sys.exit(1)

    print(f'\n市场分布:')
    print(df['market_name'].value_counts())
    print(f'\n前 10 只股票:')
    print(df[['ts_code', 'name', 'market_name', 'industry', 'list_date']].head(10))

    print('\n' + '=' * 60)
    print('保存数据...')
    print('=' * 60)

    config = load_config()
    storage_config = config.get('storage', {}).get('postgresql', {})
    storage = PostgreSQLStorage(storage_config)
    storage.connect()

    create_stock_list_table(storage)

    if save_to_database(df, storage):
        save_to_parquet(df)

        cursor = storage.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM stock_list')
        count = cursor.fetchone()[0]
        print(f'\n📊 数据库中共有 {count} 条记录')

        cursor.execute('SELECT market_name, COUNT(*) FROM stock_list GROUP BY market_name')
        result = cursor.fetchall()
        print('\n市场分布:')
        for row in result:
            print(f'  {row[0]}: {row[1]}')

        cursor.close()

    storage.disconnect()

    print('\n🎉 股票列表更新完成！')


if __name__ == '__main__':
    main()
