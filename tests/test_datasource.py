#!/usr/bin/env python3
"""测试 datasource.get_kline """
import sys
sys.path.insert(0, '/Users/zhangk/workspace/Quantitative_trading/backend')

from collector.datasource.baostock import BaostockDataSource
import pandas as pd

datasource = BaostockDataSource()

# 测试获取数据
print('=== 测试 datasource.get_kline ===')
df = datasource.get_kline('sz.000001', 'daily', '2026-05-01', '2026-05-10')

if df is not None and not df.empty:
    print(f'✅ 获取到 {len(df)} 条数据')
    print(f'\n列名: {df.columns.tolist()}')
    print(f'\n数据类型:')
    for col in df.columns:
        print(f'  {col}: {df[col].dtype}')
    print(f'\n前3行数据:')
    print(df.head(3))
else:
    print('❌ 未获取到数据')
