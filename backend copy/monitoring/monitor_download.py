#!/usr/bin/env python3
"""
数据下载监控启动脚本

用法:
    python scripts/monitor_download.py --task daily      # 监控日线数据导入
    python scripts/monitor_download.py --task minute     # 监控分钟数据导入
    python scripts/monitor_download.py --cmd "your_command"  # 监控自定义命令
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from utils.monitor import ExternalProcessMonitor


def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    parser = argparse.ArgumentParser(description='数据下载监控程序')
    parser.add_argument('--task', type=str, choices=['daily', 'minute'], 
                        help='预设任务类型: daily(日线数据), minute(分钟数据)')
    parser.add_argument('--cmd', type=str, help='自定义要监控的命令')
    parser.add_argument('--max-retries', type=int, default=5, help='最大重试次数')
    parser.add_argument('--timeout', type=int, default=300, help='超时阈值(秒)')
    parser.add_argument('--heartbeat', type=int, default=30, help='心跳检测间隔(秒)')
    
    args = parser.parse_args()
    
    # 确定要监控的命令和任务名称
    if args.task == 'daily':
        task_name = "日线数据导入"
        command = "python scripts/import_daily_data.py"
    elif args.task == 'minute':
        task_name = "分钟数据导入"
        command = "python scripts/import_minute_data.py"
    elif args.cmd:
        task_name = "自定义任务"
        command = args.cmd
    else:
        parser.print_help()
        sys.exit(1)
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 创建监控器
    monitor = ExternalProcessMonitor(
        task_name=task_name,
        command=command,
        cwd=project_root,
        max_retries=args.max_retries,
        heartbeat_interval=args.heartbeat,
        timeout_threshold=args.timeout,
        base_retry_delay=60,
        max_retry_delay=3600
    )
    
    logger.info(f"🎯 启动 {task_name} 监控程序")
    logger.info(f"📋 命令: {command}")
    logger.info(f"⚙️  最大重试: {args.max_retries}次")
    logger.info(f"⏱️  超时阈值: {args.timeout}秒")
    logger.info(f"❤️  心跳间隔: {args.heartbeat}秒")
    
    try:
        monitor.start()
        monitor.wait()
    except KeyboardInterrupt:
        logger.info("⏹️  收到中断信号，正在停止监控...")
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()
