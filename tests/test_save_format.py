#!/usr/bin/env python3
"""测试保存不同格式的 trade_date """
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')

from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
import pandas as pd

# 获取数据
datasource = BaostockDataSource()
df = datasource.get_kline('sz.000001', 'daily', '2026-05-01', '2026-05-10')

print('=== datasource.get_kline 返回的数据 ===')
print(f'列名: {df.columns.tolist()}')
print(f'trade_date 类型: {df["trade_date"].dtype}')
print(f'trade_date 示例: {df["trade_date"].iloc[0]}')

# 准备保存
df['code'] = '000001'
df['cycle'] = '1d'
df['adjust_type'] = 'qfq'
df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')

# 只保留需要的列
required_columns = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 
                  'close', 'pre_close', 'volume', 'amount', 'adjust_type', 
                  'trade_datetime']
df_save = df[required_columns].copy()

print('\n=== 保存前的数据 ===')
print(f'trade_date 类型: {df_save["trade_date"].dtype}')
print(df_save)

# 保存
storage = PostgreSQLStorage(config.storage.get('postgresql', {}))
storage.connect()

try:
    count = storage.save_quotes(df_save)
    print(f'\n✅ 保存成功: {count} 条')
except Exception as e:
    print(f'\n❌ 保存失败: {e}')
    import traceback
    traceback.print_exc()

storage.disconnect()
