#!/usr/bin/env python3
"""添加昨收字段并计算数据（分批处理）"""
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
    
    # 1. 添加 pre_close 字段
    print('🔧 正在添加 pre_close 字段...')
    try:
        cursor.execute('''
            ALTER TABLE stock_quotes 
            ADD COLUMN IF NOT EXISTS pre_close NUMERIC(10, 2)
        ''')
        storage.conn.commit()
        print('✅ pre_close 字段添加成功')
    except Exception as e:
        print(f'❌ 添加字段失败: {e}')
        storage.conn.rollback()
        storage.disconnect()
        return
    
    # 2. 检查数据量
    cursor.execute('SELECT COUNT(*) FROM stock_quotes')
    total_count = cursor.fetchone()[0]
    print(f'\n� stock_quotes 表共有 {total_count} 条数据')
    
    # 3. 获取所有唯一的股票代码
    cursor.execute('SELECT DISTINCT code FROM stock_quotes ORDER BY code')
    codes = [row[0] for row in cursor.fetchall()]
    print(f'📈 共有 {len(codes)} 只股票')
    
    # 4. 分批处理每只股票
    updated_count = 0
    batch_size = 100
    
    for i, code in enumerate(codes):
        try:
            # 使用窗口函数 LAG 获取上一日收盘价作为昨收
            cursor.execute('''
                UPDATE stock_quotes sq
                SET pre_close = prev_close
                FROM (
                    SELECT 
                        code, 
                        trade_date, 
                        LAG(close) OVER (PARTITION BY code ORDER BY trade_date) AS prev_close
                    FROM stock_quotes
                    WHERE code = %s
                ) AS prev_data
                WHERE sq.code = prev_data.code 
                  AND sq.trade_date = prev_data.trade_date
                  AND prev_data.prev_close IS NOT NULL
                  AND sq.pre_close IS NULL
            ''', (code,))
            
            updated_count += cursor.rowcount
            
            # 每处理一批提交一次
            if (i + 1) % batch_size == 0:
                storage.conn.commit()
                print(f'已处理 {i + 1}/{len(codes)} 只股票...')
        
        except Exception as e:
            print(f'❌ 处理股票 {code} 失败: {e}')
            storage.conn.rollback()
    
    # 最后提交
    storage.conn.commit()
    print(f'\n✅ 成功更新 {updated_count} 条记录的昨收数据')
    
    # 5. 验证结果
    print('\n🔍 验证昨收数据:')
    cursor.execute('''
        SELECT code, trade_date, pre_close, close
        FROM stock_quotes 
        WHERE pre_close IS NOT NULL
        ORDER BY code, trade_date
        LIMIT 5
    ''')
    result = cursor.fetchall()
    for row in result:
        print(f'  {row[0]} | {row[1]} | 昨收:{row[2]} | 收盘:{row[3]}')
    
    cursor.close()
    storage.disconnect()

if __name__ == '__main__':
    main()
