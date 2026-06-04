#!/usr/bin/env python3
"""
清理重复的行情数据
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
    print("🧹 清理重复的行情数据")
    print("=" * 60)

    # 查询重复记录的数量
    cursor.execute("""
        SELECT COUNT(*) 
        FROM (
            SELECT code, cycle, trade_date, COUNT(*) 
            FROM stock_quotes 
            WHERE trade_date = %s 
            GROUP BY code, cycle, trade_date 
            HAVING COUNT(*) > 1
        ) t
    """, ('2026-06-01',))
    duplicate_groups = cursor.fetchone()[0]
    print(f"\n📊 发现 {duplicate_groups} 组重复记录")

    # 删除重复记录，只保留最新的一条
    print("\n🔄 开始清理重复记录...")
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
    
    deleted_count = cursor.rowcount
    storage.conn.commit()
    print(f"✅ 删除了 {deleted_count} 条重复记录")

    # 验证清理结果
    print("\n📊 验证清理结果...")
    cursor.execute("""
        SELECT COUNT(DISTINCT code), COUNT(*) 
        FROM stock_quotes 
        WHERE trade_date = %s
    """, ('2026-06-01',))
    stock_count, total_count = cursor.fetchone()
    print(f"✅ 清理后：{stock_count} 只股票，{total_count} 条记录")

    cursor.close()
    storage.disconnect()
    
    print("\n" + "=" * 60)
    print("✅ 清理完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
