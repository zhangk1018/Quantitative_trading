#!/usr/bin/env python3
"""
专门检查 2026-06-01 的数据
"""
import sys
sys.path.insert(0, '.')

from utils.config import config
from utils.storage_factory import StorageFactory

def main():
    storage = StorageFactory.create_storage(config.get('storage'))
    storage.connect()

    cursor = storage.conn.cursor()

    print("=" * 60)
    print("📊 2026-06-01 数据检查")
    print("=" * 60)

    # 检查总记录数和股票数
    cursor.execute("""
        SELECT COUNT(DISTINCT code), COUNT(*)
        FROM stock_quotes
        WHERE trade_date = %s
    """, ('2026-06-01',))
    stock_count, total_count = cursor.fetchone()
    print(f"\n📈 2026-06-01: {stock_count} 只股票, {total_count} 条记录")

    # 检查是否有重复记录
    cursor.execute("""
        SELECT code, COUNT(*) as cnt
        FROM stock_quotes
        WHERE trade_date = %s
        GROUP BY code, cycle, trade_date
        HAVING COUNT(*) > 1
    """, ('2026-06-01',))
    duplicates = cursor.fetchall()

    if duplicates:
        print(f"\n❌ 发现 {len(duplicates)} 只股票有重复记录！")
        print("\n前10只股票：")
        for code, cnt in duplicates[:10]:
            print(f"  {code}: {cnt} 条")
    else:
        print("\n✅ 没有重复记录！完美！")

    cursor.close()
    storage.disconnect()

if __name__ == '__main__':
    main()
