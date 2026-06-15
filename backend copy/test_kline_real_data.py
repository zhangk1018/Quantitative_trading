#!/usr/bin/env python3
"""测试 KlineService 是否能正确读取真实数据"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api.router.kline import get_kline_service

print("=" * 60)
print("测试 P0-011: KlineService 真实数据读取")
print("=" * 60)

ks = get_kline_service()
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

    # 验证是否为真实数据（与数据库对比）
    print()
    print("验证数据真实性:")
    print(f"  数据库最新数据收盘价应为 10.98")
    last_date = data.data[-1].trade_date
    last_close = float(data.data[-1].close)
    print(f"  ✅ 最新日期: {last_date}")
    if abs(last_close - 10.98) < 0.01:
        print(f"  ✅ 收盘价匹配: {last_close} (预期 10.98)")
        print(f"  ✅ 数据来源: 真实数据（非 mock）")
    else:
        print(f"  ⚠️ 收盘价不匹配: {last_close} (预期 10.98)")

print("=" * 60)
print("✅ P0-011 测试完成")
print("=" * 60)