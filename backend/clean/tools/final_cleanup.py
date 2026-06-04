#!/usr/bin/env python3
"""
最终全面清理重复数据
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
    print("🧹 最终全面清理重复数据")
    print("=" * 60)

    # 不断清理直到没有重复记录
    iteration = 1
    while True:
        print(f"\n🔄 第 {iteration} 次清理...")
        
        # 查找重复记录
        cursor.execute("""
            SELECT code, COUNT(*) as cnt
            FROM stock_quotes
            WHERE trade_date = %s
            GROUP BY code, cycle, trade_date
            HAVING COUNT(*) > 1
        """, ('2026-06-01',))
        
        duplicates = cursor.fetchall()
        
        if not duplicates:
            print("✅ 没有重复记录了！")
            break
        
        print(f"📊 发现 {len(duplicates)} 组重复记录")
        
        # 删除重复记录，保留 id 最大的一条
        cursor.execute("""
            DELETE FROM stock_quotes
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM stock_quotes
                WHERE trade_date = %s
                GROUP BY code, cycle, trade_date
            )
            AND trade_date = %s
        """, ('2026-06-01', '2026-06-01'))
        
        deleted = cursor.rowcount
        storage.conn.commit()
        print(f"🗑️ 删除了 {deleted} 条重复记录")
        
        iteration += 1

    # 最终验证
    print("\n" + "=" * 60)
    print("📊 最终验证")
    print("=" * 60)
    
    cursor.execute("""
        SELECT COUNT(DISTINCT code), COUNT(*)
        FROM stock_quotes
        WHERE trade_date = %s
    """, ('2026-06-01',))
    stock_count, total_count = cursor.fetchone()
    print(f"✅ 2026-06-01: {stock_count} 只股票, {total_count} 条记录")
    
    cursor.close()
    storage.disconnect()
    
    print("\n" + "=" * 60)
    print("🎉 清理完成！")
    print("=" * 60)

if __name__ == '__main__':
    main()
