import pandas as pd
df = pd.read_parquet('/Users/zhangk/workspace/Quantitative_trading/data/price/daily/latest_quotes.parquet')

mc = df['market_cap'].dropna()
print('=== market_cap 分布（单位：万元）===')
print(f'总数: {len(mc)}')
print(f'< 1亿(10000万): {(mc < 10000).sum()} 只')
print(f'1~5亿(10000~50000万): {((mc >= 10000) & (mc < 50000)).sum()} 只')
print(f'5~10亿(50000~100000万): {((mc >= 50000) & (mc < 100000)).sum()} 只')
print(f'10~20亿(100000~200000万): {((mc >= 100000) & (mc < 200000)).sum()} 只')
print(f'20~50亿(200000~500000万): {((mc >= 200000) & (mc < 500000)).sum()} 只')
print(f'50~100亿(500000~1000000万): {((mc >= 500000) & (mc < 1000000)).sum()} 只')
print(f'100~500亿(1000000~5000000万): {((mc >= 1000000) & (mc < 5000000)).sum()} 只')
print(f'>500亿(5000000万): {(mc >= 5000000).sum()} 只')
print()
# 1.2~1.5亿区间
print(f'1.2~1.5亿(12000~15000万): {((mc >= 12000) & (mc < 15000)).sum()} 只')
print(f'1~2亿(10000~20000万): {((mc >= 10000) & (mc < 20000)).sum()} 只')
print(f'0.5~3亿(5000~30000万): {((mc >= 5000) & (mc < 30000)).sum()} 只')
print()
# 查看 1.2~1.5亿的股票
small = df[(df['market_cap'] >= 12000) & (df['market_cap'] < 15000)]
print(f'1.2~1.5亿的股票: {len(small)} 只')
if len(small) > 0:
    for _, r in small.iterrows():
        print(f'  {r["code"]} {r["stock_name"]:10s} mc={r["market_cap"]:.2f}')
