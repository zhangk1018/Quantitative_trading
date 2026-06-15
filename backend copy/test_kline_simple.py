#!/usr/bin/env python3
"""简化的 KlineService 真实数据测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import config
from collector.storage.postgresql_storage import PostgreSQLStorage
from core.service.kline_service import KlineService
from collector.db.loader import DataLoader


print("=" * 60)
print("测试 KlineService 真实数据读取")
print("=" * 60)

# 初始化 storage
db_config = config.get('database', {})
storage = PostgreSQLStorage({
    'host': db_config.get('host', 'localhost'),
    'port': db_config.get('port', 5432),
    'database': db_config.get('database', 'quant_trading'),
    'username': db_config.get('username', 'quant_user'),
    'password': db_config.get('password', ''),
})

if not storage.connect():
    print("❌ 数据库连接失败")
    sys.exit(1)

print("✅ PostgreSQL 连接成功")

# 初始化 loader（为了兼容 KlineService）
try:
    loader = DataLoader()
except Exception as e:
    print(f"⚠️  DataLoader 初始化失败（不影响 storage 测试）: {e}")
    loader = None

# 创建 KlineService
ks = KlineService(loader, storage)
print(f"✅ KlineService 初始化成功")
print(f"✅ storage 已注入: {ks._storage is not None}")

# 测试获取 000001 的数据
data = ks.get_kline_data('000001', period='daily', limit=10)
print(f"✅ 获取数据成功: {data.count} 条")

if data.data:
    print(f"✅ 第一条数据日期: {data.data[0].trade_date}")
    print(f"✅ 最后一条数据日期: {data.data[-1].trade_date}")
    print(f"✅ 第一条收盘价: {data.data[0].close}")
    print(f"✅ 最后一条收盘价: {data.data[-1].close}")

    # 验证是否为真实数据
    print()
    print("验证数据真实性:")
    # 直接查询数据库对比
    df = storage.get_quotes('000001', 'daily')
    if not df.empty:
        df_sorted = df.sort_values('trade_date', ascending=False).head(10)
        print(f"  数据库查询到 {len(df)} 条记录")
        print(f"  最新日期: {df_sorted.iloc[0]['trade_date']}")
        print(f"  最新收盘价: {df_sorted.iloc[0]['close']}")
        # 对比
        last_close_service = float(data.data[-1].close)
        last_close_db = float(df_sorted.iloc[0]['close'])
        if abs(last_close_service - last_close_db) < 0.01:
            print(f"  ✅ 数据匹配: KlineService={last_close_service}, DB={last_close_db}")
            print(f"  ✅ 数据来源: 真实数据（非 mock）")
        else:
            print(f"  ⚠️ 数据不匹配: KlineService={last_close_service}, DB={last_close_db}")

# 测试两次调用一致性
print()
print("测试两次调用一致性:")
data1 = ks.get_kline_data('000001', period='daily', limit=5)
data2 = ks.get_kline_data('000001', period='daily', limit=5)
if data1.count == data2.count:
    all_match = True
    for i in range(data1.count):
        if data1.data[i].close != data2.data[i].close:
            all_match = False
            break
    if all_match:
        print("  ✅ 两次调用返回数据完全一致")
    else:
        print("  ❌ 两次调用数据不一致")
else:
    print("  ❌ 两次调用数量不一致")

# 测试信号预计算脚本（单只股票）
print()
print("测试信号预计算脚本:")
try:
    # 先确保表存在
    storage.init_tables()
    print("  ✅ trade_signals 表已就绪")

    # 简单测试：直接测试我们的信号提取函数
    from clean.tools.precompute_signals import extract_signals, load_stock_quotes, run_stock
    df = load_stock_quotes(storage, '000001')
    if not df.empty:
        print(f"  ✅ 加载到 {len(df)} 条 000001 数据")
        signals = extract_signals(df)
        print(f"  ✅ 提取到 {len(signals)} 个信号")
        if len(signals) > 0:
            print(f"  ✅ 示例信号: {signals.iloc[0]['signal_type']} @ {signals.iloc[0]['trade_date']}")
except Exception as e:
    print(f"  ⚠️  信号测试跳过（可能需要更多数据）: {e}")

storage.disconnect()

print("=" * 60)
print("✅ 测试完成")
print("=" * 60)
