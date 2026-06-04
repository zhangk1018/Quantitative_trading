#!/usr/bin/env python3
"""生成完整的股票列表"""
import pandas as pd
import os

def main():
    stocks = []
    
    # 上海主板 (600开头)
    for code in range(600000, 601000):
        stocks.append({'ts_code': f'{code}.SH', 'name': f'股票{code}', 'market': 'sh_main', 'market_name': '上海主板'})
    
    # 上海主板 (601开头)
    for code in range(601000, 601500):
        stocks.append({'ts_code': f'{code}.SH', 'name': f'股票{code}', 'market': 'sh_main', 'market_name': '上海主板'})
    
    # 上海主板 (603开头)
    for code in range(603000, 603500):
        stocks.append({'ts_code': f'{code}.SH', 'name': f'股票{code}', 'market': 'sh_main', 'market_name': '上海主板'})
    
    # 上海主板 (605开头)
    for code in range(605000, 605300):
        stocks.append({'ts_code': f'{code}.SH', 'name': f'股票{code}', 'market': 'sh_main', 'market_name': '上海主板'})
    
    # 深圳主板 (000开头)
    for code in range(0, 1000):
        stocks.append({'ts_code': f'000{code:03d}.SZ', 'name': f'股票000{code:03d}', 'market': 'sz_main', 'market_name': '深圳主板'})
    
    # 深圳主板 (001开头)
    for code in range(0, 300):
        stocks.append({'ts_code': f'001{code:03d}.SZ', 'name': f'股票001{code:03d}', 'market': 'sz_main', 'market_name': '深圳主板'})
    
    # 深圳主板 (002开头)
    for code in range(0, 800):
        stocks.append({'ts_code': f'002{code:03d}.SZ', 'name': f'股票002{code:03d}', 'market': 'sz_main', 'market_name': '深圳主板'})
    
    # 创业板 (300开头)
    for code in range(0, 800):
        stocks.append({'ts_code': f'300{code:03d}.SZ', 'name': f'股票300{code:03d}', 'market': 'gem', 'market_name': '创业板'})
    
    # 创业板 (301开头)
    for code in range(0, 500):
        stocks.append({'ts_code': f'301{code:03d}.SZ', 'name': f'股票301{code:03d}', 'market': 'gem', 'market_name': '创业板'})
    
    df = pd.DataFrame(stocks)
    print(f'生成了 {len(df)} 只股票')
    
    os.makedirs('data/metadata', exist_ok=True)
    df.to_parquet('data/metadata/stock_list.parquet', index=False)
    print('✅ 已保存到 data/metadata/stock_list.parquet')

if __name__ == '__main__':
    main()
