#!/usr/bin/env python3
"""
监控数据导入程序执行情况
每30秒检查一次数据是否在增长
"""
import sys
import time
from datetime import datetime

sys.path.insert(0, '.')

from utils.config import config
from utils.storage_factory import StorageFactory

def get_data_count(storage):
    """获取2026年6月1日的数据量"""
    cursor = storage.conn.cursor()
    cursor.execute('SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE trade_date = %s', ('2026-06-01',))
    stock_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stock_quotes WHERE trade_date = %s', ('2026-06-01',))
    total_count = cursor.fetchone()[0]
    cursor.close()
    return stock_count, total_count

def main():
    print("=" * 60)
    print("📊 数据导入监控程序启动")
    print("=" * 60)
    
    # 初始化存储
    storage = StorageFactory.create_storage(config.get('storage'))
    if not storage.connect():
        print("❌ 数据库连接失败")
        return
    
    try:
        last_stock_count = None
        last_total_count = None
        stagnant_count = 0
        
        while True:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            stock_count, total_count = get_data_count(storage)
            
            print(f"\n🕐 [{current_time}]")
            print(f"📈 已有数据的股票数量: {stock_count}")
            print(f"📝 总记录数量: {total_count}")
            
            if last_stock_count is not None and last_total_count is not None:
                stock_growth = stock_count - last_stock_count
                total_growth = total_count - last_total_count
                
                if stock_growth > 0 or total_growth > 0:
                    print(f"✅ 数据在增长: +{stock_growth}只股票, +{total_growth}条记录")
                    stagnant_count = 0
                else:
                    stagnant_count += 1
                    print(f"⚠️ 数据停止增长 (已停止 {stagnant_count}次检查)")
                    
                    if stagnant_count >= 3:
                        print("\n" + "=" * 60)
                        print("❌ 程序可能已停滞，建议检查日志！")
                        print("=" * 60)
            
            last_stock_count = stock_count
            last_total_count = total_count
            
            print(f"\n⏳ 等待30秒后继续检查...")
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n\n👋 监控程序已停止")
    except Exception as e:
        print(f"\n❌ 监控出错: {str(e)}")
    finally:
        storage.disconnect()

if __name__ == '__main__':
    main()
