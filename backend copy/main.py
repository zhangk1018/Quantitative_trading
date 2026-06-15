#!/usr/bin/env python3
"""
量化数据获取与清洗模块 - 主运行脚本

使用方式:
python main.py init              # 初始化数据库
python main.py update_stock_list # 更新股票列表
python main.py update_calendar   # 更新交易日历
python main.py update_quotes     # 更新所有行情数据
python main.py update_single <code> <cycle>  # 更新单股票单周期
python main.py query <code> <cycle>  # 查询股票数据
python main.py start_scheduler   # 启动定时任务
python main.py status            # 查看状态
python main.py test              # 运行测试
"""
import sys
import os

# 添加 backend 目录到系统路径
sys.path.append(os.path.dirname(__file__))

from core.service.data_service import DataService
from task_scheduler import TaskScheduler
from utils.logger import setup_logger

logger = setup_logger('main')

# 数据目录配置
DATA_DIRS = [
    'data',
    'data/backup',
    'data/snapshot/latest'
]


def init_data_directories():
    """初始化数据目录 - 检查并创建必要的目录"""
    print("📁 初始化数据目录...")
    for dir_path in DATA_DIRS:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"  ✅ 创建目录: {dir_path}")
        else:
            print(f"  ✅ 目录已存在: {dir_path}")
    print("")


def print_usage():
    """打印使用说明"""
    print("=" * 60)
    print("量化数据获取与清洗模块")
    print("=" * 60)
    print("使用方式:")
    print("  python main.py init              # 初始化数据库")
    print("  python main.py update_stock_list # 更新股票列表")
    print("  python main.py update_calendar   # 更新交易日历")
    print("  python main.py update_quotes     # 更新所有行情数据（全量）")
    print("  python main.py update_main_board # 更新沪深主板+创业板")
    print("  python main.py update_snapshot   # 更新实时快照")
    print("  python main.py update_single <code> <cycle>  # 更新单股票单周期")
    print("  python main.py query <code> <cycle>  # 查询股票数据")
    print("  python main.py start_scheduler   # 启动定时任务")
    print("  python main.py status            # 查看状态")
    print("  python main.py test              # 运行测试")
    print("")
    print("支持的周期: daily, min5, min15, min30, min60")
    print("=" * 60)


def init_database():
    """初始化数据库"""
    # 先初始化数据目录
    init_data_directories()
    
    service = DataService()
    if service.connect():
        print("✅ 数据库初始化成功")
        stats = service.get_stats()
        print(f"股票数量: {stats['stock_count']}")
        print(f"行情数据: {stats['total_quotes_count']}")
        print(f"交易日历: {stats.get('calendar_count', 0)} 天")
        service.disconnect()
    else:
        print("❌ 数据库初始化失败")


def update_stock_list():
    """更新股票列表"""
    service = DataService()
    
    if service.connect():
        print("✅ 连接成功")
        print("开始更新股票列表...")
        
        service.update_stock_basic()
        
        stocks = service.get_stock_list()
        print(f"\n📋 股票列表统计:")
        print(f"  总股票数: {len(stocks)}")
        
        service.disconnect()
        print("\n✅ 更新完成")
    else:
        print("❌ 连接失败")


def update_calendar():
    """更新交易日历"""
    service = DataService()
    
    if service.connect():
        print("✅ 连接成功")
        print("开始更新交易日历...")
        
        service.update_trade_calendar()
        
        stats = service.get_stats()
        print(f"\n📅 交易日历统计:")
        print(f"  总天数: {stats.get('calendar_count', 0)}")
        
        service.disconnect()
        print("\n✅ 更新完成")
    else:
        print("❌ 连接失败")


def update_quotes():
    """更新所有行情数据"""
    scheduler = TaskScheduler()
    scheduler.manual_update()


def update_main_board():
    """更新沪深主板和创业板（排除科创板和北交所）"""
    scheduler = TaskScheduler()
    # 沪深主板: sh.60xxxx, sz.00xxxx
    # 创业板: sz.30xxxx
    stock_filter = ['sh.60', 'sz.00', 'sz.30']
    scheduler.manual_update(stock_filter=stock_filter)


def update_snapshot():
    """手动更新实时快照"""
    from core.service.data_service import DataService
    
    print("📊 手动更新实时快照...")
    
    service = DataService()
    if service.connect():
        success = service.update_snapshot()
        service.disconnect()
        
        if success:
            print("✅ 快照更新成功")
        else:
            print("❌ 快照更新失败")
    else:
        print("❌ 连接失败")


def update_single(code: str, cycle: str):
    """更新单股票单周期"""
    service = DataService()
    
    if service.connect():
        print(f"✅ 连接成功")
        print(f"开始更新 {code} {cycle} 数据...")
        
        service.download_quotes(code, cycle)
        
        last_date = service.get_last_date(code, cycle)
        print(f"✅ 更新成功，最新日期: {last_date}")
        
        service.disconnect()
    else:
        print("❌ 连接失败")


def query_data(code: str, cycle: str):
    """查询股票数据"""
    service = DataService()
    
    if service.connect():
        df = service.get_quotes(code, cycle)
        
        if df.empty:
            print(f"❌ 未找到 {code} {cycle} 数据")
        else:
            print(f"\n📊 查询结果: {len(df)} 条数据")
            print("-" * 60)
            print(df.head(10))
        
        service.disconnect()
    else:
        print("❌ 连接失败")


def show_status():
    """显示系统状态"""
    service = DataService()
    
    if service.connect():
        stats = service.get_stats()
        
        print("=" * 60)
        print("📊 系统状态")
        print("=" * 60)
        print(f"股票数量: {stats['stock_count']}")
        print(f"行情数据: {stats['total_quotes_count']}")
        print(f"已存储周期: {stats['cycles']}")
        print(f"交易日历: {stats.get('calendar_count', 0)} 天")
        print("=" * 60)
        
        service.disconnect()
    else:
        print("❌ 连接失败")


def run_tests():
    """运行测试"""
    print("=" * 60)
    print("🧪 运行测试")
    print("=" * 60)
    
    # 测试1: 测试数据服务连接
    print("\n1. 测试数据服务...")
    service = DataService()
    if service.connect():
        print("   ✅ 数据服务连接成功")
        
        # 测试交易日历
        print("\n2. 测试交易日历...")
        service.update_trade_calendar()
        stats = service.get_stats()
        print(f"   ✅ 交易日历: {stats.get('calendar_count', 0)} 天")
        
        # 测试股票列表
        print("\n3. 测试股票列表...")
        service.update_stock_basic()
        stocks = service.get_stock_list()
        print(f"   ✅ 股票列表: {len(stocks)} 只")
        
        # 测试单股票数据下载
        print("\n4. 测试数据下载...")
        if not stocks.empty:
            test_code = stocks.iloc[0]['code']
            service.download_quotes(test_code, 'daily')
            data = service.get_quotes(test_code, 'daily')
            print(f"   ✅ {test_code} 日线数据: {len(data)} 条")
        
        service.disconnect()
    else:
        print("   ❌ 数据服务连接失败")
    
    # 测试5: 测试数据质量校验
    print("\n5. 测试数据质量校验...")
    from clean.processor.data_processor import DataProcessor
    import pandas as pd
    
    test_data = pd.DataFrame({
        'code': ['600000', '600000', '600000'],
        'trade_date': ['2025-05-20', '2025-05-20', '2025-05-21'],
        'cycle': ['daily', 'daily', 'daily'],
        'open': [10.0, 10.0, -5.0],      # 包含负数异常
        'high': [10.5, 10.5, 10.0],
        'low': [9.5, 9.5, 9.0],
        'close': [10.2, 10.2, 9.5],
        'volume': [10000, 10000, 0],      # 包含零成交量
        'amount': [102000, 102000, 0]
    })
    
    processor = DataProcessor()
    validation = processor.validate_data(test_data)
    print(f"   ✅ 数据验证: {validation}")
    
    cleaned = processor.process(test_data)
    print(f"   ✅ 数据清洗: {len(test_data)} -> {len(cleaned)} 条")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试完成")
    print("=" * 60)


def start_scheduler():
    """启动定时任务"""
    print("启动定时任务调度器...")
    print("按 Ctrl+C 停止")
    scheduler = TaskScheduler()
    scheduler.start()


def main():
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1]
    
    if command == 'help':
        print_usage()
    
    elif command == 'init':
        init_database()
    
    elif command == 'update_stock_list':
        update_stock_list()
    
    elif command == 'update_calendar':
        update_calendar()
    
    elif command == 'update_quotes':
        update_quotes()

    elif command == 'update_main_board':
        update_main_board()

    elif command == 'update_snapshot':
        update_snapshot()

    elif command == 'update_single':
        if len(sys.argv) < 4:
            print("用法: python main.py update_single <code> <cycle>")
            return
        code = sys.argv[2]
        cycle = sys.argv[3]
        update_single(code, cycle)
    
    elif command == 'query':
        if len(sys.argv) < 4:
            print("用法: python main.py query <code> <cycle>")
            return
        code = sys.argv[2]
        cycle = sys.argv[3]
        query_data(code, cycle)
    
    elif command == 'start_scheduler':
        start_scheduler()
    
    elif command == 'status':
        show_status()
    
    elif command == 'test':
        run_tests()
    
    else:
        print(f"未知命令: {command}")
        print_usage()


if __name__ == '__main__':
    main()
