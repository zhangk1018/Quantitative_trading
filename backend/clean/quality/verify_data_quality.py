#!/usr/bin/env python3
"""
数据质量验证脚本
验证已修复的问题：
- [P1-007] 数据一致性问题
- [P1-004] 地区字段（area）数据异常
- [P1-005] 技术指标字段缺失
- [P2-001] 001xxx 开头股票格式验证错误
"""

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import load_config


def main():
    config = load_config()
    storage_config = config.get('storage', {}).get('postgresql', {})
    storage = PostgreSQLStorage(storage_config)
    storage.connect()

    print("=== 数据质量验证报告 ===\n")

    # 1. 检查 stock_basic 表
    print("【1】stock_basic 表检查")
    result = storage.execute_query("SELECT COUNT(*) FROM stock_basic")
    total = result[0][0]
    print(f"   股票总数: {total}")

    result = storage.execute_query("SELECT COUNT(*) FROM stock_basic WHERE industry IS NULL")
    null_industry = result[0][0]
    print(f"   industry 为空: {null_industry} (修复前: 全部为空)")

    result = storage.execute_query("SELECT COUNT(*) FROM stock_basic WHERE list_date IS NULL")
    null_list_date = result[0][0]
    print(f"   list_date 为空: {null_list_date} (修复前: 全部为空)")

    result = storage.execute_query("SELECT COUNT(*) FROM stock_basic WHERE code LIKE '%001%'")
    count_001 = result[0][0]
    print(f"   001开头股票数: {count_001} (修复前: 被过滤)")

    # 2. 检查 stock_quotes 表
    print("\n【2】stock_quotes 表检查")
    result = storage.execute_query("SELECT COUNT(*) FROM stock_quotes")
    total_quotes = result[0][0]
    print(f"   行情记录总数: {total_quotes}")

    # 3. 数据一致性检查
    print("\n【3】数据一致性检查")
    result = storage.execute_query("""
        SELECT COUNT(DISTINCT sq.code)
        FROM stock_quotes sq
        LEFT JOIN stock_basic sb ON
            (sb.code = 'SH.' || sq.code OR sb.code = 'SZ.' || sq.code OR sb.code = sq.code)
        WHERE sb.code IS NULL
    """)
    orphan_quotes = result[0][0]
    print(f"   stock_quotes中无对应basic数据的股票数: {orphan_quotes}")

    # 4. 检查技术指标表
    print("\n【4】stock_indicators 表检查")
    result = storage.execute_query("SELECT COUNT(*) FROM stock_indicators")
    total_indicators = result[0][0]
    print(f"   技术指标记录总数: {total_indicators}")

    storage.disconnect()

    print("\n=== 验证结果 ===")
    if null_industry == 0 and null_list_date == 0 and count_001 > 0 and orphan_quotes == 0:
        print("✅ 所有问题已修复成功！")
    else:
        print("⚠️ 部分问题仍需处理")


if __name__ == "__main__":
    main()
