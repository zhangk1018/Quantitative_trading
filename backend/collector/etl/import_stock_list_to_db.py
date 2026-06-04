#!/usr/bin/env python3
"""将 stock_list.parquet 导入数据库（修复版）"""
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/src')

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config
import pandas as pd

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

def import_parquet_to_db(storage, parquet_path):
    """将 parquet 文件导入数据库"""
    # 读取 parquet 文件
    df = pd.read_parquet(parquet_path)
    print(f'📥 读取到 {len(df)} 条数据')
    
    # 数据预处理
    df['list_date'] = pd.to_datetime(df['list_date'], errors='coerce')
    df['outDate'] = pd.to_datetime(df['outDate'], errors='coerce')
    
    # 将 NaT 转换为 None
    df['list_date'] = df['list_date'].apply(lambda x: x.date() if pd.notna(x) else None)
    df['outDate'] = df['outDate'].apply(lambda x: x.date() if pd.notna(x) else None)
    
    # 将空字符串转换为 None
    df = df.replace({'': None})
    
    cursor = storage.conn.cursor()
    success_count = 0
    fail_count = 0
    
    # 使用 COPY 批量导入
    from io import StringIO
    
    output = StringIO()
    for _, row in df.iterrows():
        # 构建 CSV 行
        line = '\t'.join([
            row['ts_code'],
            row['name'],
            str(row['list_date']) if row['list_date'] else '',
            str(row['outDate']) if row['outDate'] else '',
            row['type'] if row['type'] else '',
            row['status'] if row['status'] else '',
            row['market'] if row['market'] else '',
            row['market_name'] if row['market_name'] else '',
            row['code'] if row['code'] else '',
            row['industry'] if row['industry'] else ''
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
        success_count = len(df)
        print(f'✅ 批量导入成功：{success_count} 条')
    except Exception as e:
        storage.conn.rollback()
        print(f'❌ 批量导入失败：{e}')
        # 降级到逐条插入
        print('🔄 尝试逐条插入...')
        for _, row in df.iterrows():
            try:
                cursor.execute('''
                    INSERT INTO stock_list (
                        ts_code, name, list_date, out_date, type, status,
                        market, market_name, code, industry
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ts_code) DO UPDATE SET
                        name = EXCLUDED.name,
                        list_date = EXCLUDED.list_date,
                        out_date = EXCLUDED.out_date,
                        type = EXCLUDED.type,
                        status = EXCLUDED.status,
                        market = EXCLUDED.market,
                        market_name = EXCLUDED.market_name,
                        code = EXCLUDED.code,
                        industry = EXCLUDED.industry,
                        updated_at = CURRENT_TIMESTAMP
                ''', (
                    row['ts_code'],
                    row['name'],
                    row['list_date'],
                    row['outDate'],
                    row['type'],
                    row['status'],
                    row['market'],
                    row['market_name'],
                    row['code'],
                    row['industry']
                ))
                success_count += 1
            except Exception as e:
                fail_count += 1
                # 跳过失败的记录继续处理
        
        storage.conn.commit()
        print(f'✅ 逐条导入完成：成功 {success_count} 条，失败 {fail_count} 条')
    
    cursor.close()

def verify_import(storage):
    """验证导入结果"""
    cursor = storage.conn.cursor()
    
    # 查询记录数
    cursor.execute('SELECT COUNT(*) FROM stock_list')
    count = cursor.fetchone()[0]
    print(f'📊 数据库中共有 {count} 条记录')
    
    # 查询前5条
    cursor.execute('SELECT ts_code, name, market_name FROM stock_list LIMIT 5')
    result = cursor.fetchall()
    print('\n前5条数据:')
    for row in result:
        print(f'  {row[0]} | {row[1]} | {row[2]}')
    
    # 统计市场分布
    cursor.execute('SELECT market_name, COUNT(*) FROM stock_list GROUP BY market_name')
    result = cursor.fetchall()
    print('\n市场分布:')
    for row in result:
        print(f'  {row[0]}: {row[1]}')
    
    cursor.close()

def main():
    print('🚀 开始将 stock_list.parquet 导入数据库')
    
    # 加载配置
    config = load_config()
    storage_config = config.get('storage', {}).get('postgresql', {})
    
    # 连接数据库
    storage = PostgreSQLStorage(storage_config)
    storage.connect()
    
    # 创建表
    create_stock_list_table(storage)
    
    # 导入数据
    parquet_path = 'data/metadata/stock_list.parquet'
    import_parquet_to_db(storage, parquet_path)
    
    # 验证结果
    verify_import(storage)
    
    # 断开连接
    storage.disconnect()
    
    print('\n🎉 完成！股票列表已成功保存到数据库')

if __name__ == '__main__':
    main()
