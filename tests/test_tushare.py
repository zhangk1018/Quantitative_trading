#!/usr/bin/env python3
"""测试 Tushare 数据源"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# 设置 token 环境变量后直接初始化（绕过 set_token 写文件权限问题）
os.environ['TS_TOKEN'] = os.environ['TUSHARE_TOKEN']
import tushare as ts
pro = ts.pro_api(token=os.environ['TUSHARE_TOKEN'])

# 1. 测试股票列表
print('=== 测试股票列表 ===')
df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
print(f'共 {len(df)} 只股票')
print(df.head(5).to_string())

# 2. 按市场统计
print('\n=== 按交易所统计 ===')
exch_counts = df['ts_code'].str[-2:].value_counts()
print(exch_counts.to_string())

# 3. 测试K线（沪市）
print('\n=== 测试K线（浦发银行 600000.SH 近5天） ===')
kline = pro.daily(ts_code='600000.SH', start_date='20260601', end_date='20260605')
print(kline.to_string())

# 4. 测试K线（深市）
print('\n=== 测试K线（平安银行 000001.SZ 近5天） ===')
kline2 = pro.daily(ts_code='000001.SZ', start_date='20260601', end_date='20260605')
print(kline2.to_string())

# 5. 测试创业板
print('\n=== 测试K线（宁德时代 300750.SZ 近5天） ===')
kline3 = pro.daily(ts_code='300750.SZ', start_date='20260601', end_date='20260605')
print(kline3.to_string())

print('\n✅ Tushare 测试完成')