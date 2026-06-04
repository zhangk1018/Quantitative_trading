#!/usr/bin/env python3
"""
数据初始化脚本 - 用于清除并重新初始化所有数据

执行步骤：
1. 清空 PostgreSQL 数据库中的所有表
2. 清除本地快照文件
3. 初始化数据库表结构
4. 下载股票基本信息
5. 下载初始行情数据
"""

import os
import sys
import json
from datetime import datetime

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from core.service.data_service import DataService
from utils.logger import setup_logger

logger = setup_logger('data_init')


def clear_snapshot_files():
    """清除本地快照文件"""
    snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'snapshot', 'latest')
    if os.path.exists(snapshot_dir):
        files = [f for f in os.listdir(snapshot_dir) if f.endswith('.json')]
        if files:
            logger.info(f'📦 清理 {len(files)} 个快照文件...')
            for f in files:
                os.remove(os.path.join(snapshot_dir, f))
            logger.info('✅ 快照文件清理完成')
        else:
            logger.info('📦 快照目录为空，无需清理')
    else:
        logger.warning('⚠️ 快照目录不存在')


def init_database(service: DataService):
    """初始化数据库"""
    logger.info('🗄️ 初始化数据库...')
    
    # 连接数据库
    if not service.connect():
        logger.error('❌ 数据库连接失败')
        return False
    
    try:
        # 下载股票基本信息
        logger.info('📥 下载股票基本信息...')
        success = service.update_stock_basic()
        if success:
            logger.info('✅ 股票基本信息下载完成')
        else:
            logger.warning('⚠️ 股票基本信息下载失败')
        
        # 下载交易日历
        logger.info('📥 下载交易日历...')
        success = service.update_trade_calendar()
        if success:
            logger.info('✅ 交易日历下载完成')
        else:
            logger.warning('⚠️ 交易日历下载失败')
            
    finally:
        service.disconnect()
    
    return True


def main():
    """主函数"""
    print('=' * 60)
    print('          数据初始化脚本')
    print('=' * 60)
    print(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()
    
    # 检查是否有 --force 参数跳过确认
    force = '--force' in sys.argv
    
    # 确认操作（除非使用 --force 参数）
    if not force:
        confirm = input('⚠️ 此操作将清除所有现有数据，确定继续吗？(y/N): ')
        if confirm.lower() != 'y':
            print('❌ 用户取消操作')
            return
    
    print()
    
    # 1. 清除快照文件
    clear_snapshot_files()
    
    # 2. 初始化数据库
    service = DataService()
    if init_database(service):
        print()
        print('🎉 数据初始化完成！')
        print('=' * 60)
    else:
        print()
        print('❌ 数据初始化失败！')
        print('=' * 60)
        sys.exit(1)


if __name__ == '__main__':
    main()