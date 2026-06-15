#!/usr/bin/env python3
"""
定时任务调度器 - 管理所有数据同步任务

任务调度配置：
- daily_import: 每日K线数据导入（16:05）
- daily_basic_sync: 每日基本面数据同步（16:15）
- adj_factor_sync: 复权因子同步（17:00，每日一次）
- indicators_compute: 技术指标计算（16:30）
- signals_precompute: 信号预计算（16:45）
- health_check: 健康检查（每小时）
"""
import os
import sys
import subprocess
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utils.logger import setup_logger

logger = setup_logger('scheduler')


def get_task_config():
    """获取任务配置
    
    执行顺序依赖关系：
    1. daily_import (K线数据) → 2. daily_basic_sync (基本面数据)
       → 3. indicators_compute (技术指标) → 4. signals_precompute (信号)
    
    时间估算（含余量）：
    - daily_import: 15-20分钟 → 设置30分钟间隔
    - daily_basic_sync: 5分钟 → 设置10分钟间隔
    - indicators_compute: 4分钟 → 设置10分钟间隔
    - signals_precompute: 10-15分钟 → 设置20分钟间隔
    """
    tasks = {
        'daily_import': {
            'name': '每日K线数据导入',
            'script': 'collector/etl/import_daily_data.py',
            'schedule': '16:00',
            'weekdays_only': True,
            'enabled': True
        },
        'daily_basic_sync': {
            'name': '每日基本面数据同步',
            'script': 'collector/etl/sync_daily_basic.py',
            'schedule': '16:30',  # 在 daily_import 之后30分钟执行（预留20分钟导入时间+10分钟余量）
            'weekdays_only': True,
            'enabled': True
        },
        'indicators_compute': {
            'name': '技术指标计算',
            'script': 'clean/etl/compute_indicators_sample.py',
            'schedule': '16:45',  # 在 daily_basic_sync 之后15分钟执行（预留5分钟+10分钟余量）
            'weekdays_only': True,
            'enabled': True
        },
        'signals_precompute': {
            'name': '信号预计算',
            'script': 'clean/etl/signal_precompute.py',
            'schedule': '17:00',  # 在 indicators_compute 之后15分钟执行（预留4分钟+11分钟余量）
            'weekdays_only': True,
            'enabled': True
        },
        'adj_factor_sync': {
            'name': '复权因子同步',
            'script': 'collector/etl/sync_adj_factor.py',
            'schedule': '17:25',  # 在 signals_precompute 之后25分钟执行（预留15分钟+10分钟余量）
            'weekdays_only': False,
            'enabled': True
        },
        'missing_value_fix': {
            'name': '缺失值处理',
            'script': 'clean/etl/missing_value_fix.py',
            'schedule': '17:40',  # 在 adj_factor_sync 之后15分钟执行（预留5分钟+10分钟余量）
            'weekdays_only': True,
            'enabled': True
        },
        'health_check': {
            'name': '健康检查',
            'script': 'clean/etl/pipeline_health_check.py',
            'schedule': 'hourly',
            'weekdays_only': False,
            'enabled': True
        },
        'data_quality_monitor': {
            'name': '数据质量监控',
            'script': 'monitoring/data_quality_monitor.py',
            'schedule': 'hourly',
            'weekdays_only': False,
            'enabled': True
        }
    }
    return tasks


def generate_launchd_plist(task_id, task_config):
    """生成 launchd plist 配置文件"""
    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quant.{task_id}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/zhangk/workspace/Quantitative_trading/venv/bin/python</string>
        <string>/Users/zhangk/workspace/Quantitative_trading/backend/{task_config['script']}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/zhangk/workspace/Quantitative_trading</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/zhangk/workspace/Quantitative_trading/logs/scheduler/{task_id}.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/zhangk/workspace/Quantitative_trading/logs/scheduler/{task_id}.err.log</string>
    <key>RunAtLoad</key>
    <false/>
'''
    
    # 添加调度配置
    if task_config['schedule'] == 'hourly':
        plist_content += '''    <key>StartInterval</key>
    <integer>3600</integer>
'''
    else:
        hour, minute = map(int, task_config['schedule'].split(':'))
        plist_content += f'''    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
'''
        if task_config.get('weekdays_only', False):
            plist_content += '''        <key>Weekday</key>
        <array>
            <integer>1</integer>
            <integer>2</integer>
            <integer>3</integer>
            <integer>4</integer>
            <integer>5</integer>
        </array>
'''
        plist_content += '    </dict>\n'
    
    plist_content += '''</dict>
</plist>'''
    
    return plist_content


def install_launchd_plist(plist_path, task_id):
    """安装 launchd 配置"""
    try:
        # 确保 LaunchAgents 目录存在
        launch_agents_dir = os.path.expanduser('~/Library/LaunchAgents')
        os.makedirs(launch_agents_dir, exist_ok=True)
        
        # 复制到 launchd 目录
        dest_path = os.path.join(launch_agents_dir, f'com.quant.{task_id}.plist')
        subprocess.run(['cp', plist_path, dest_path], check=True)
        
        # 加载配置
        subprocess.run(['launchctl', 'load', dest_path], check=True)
        
        logger.info(f"✅ {task_id} 已安装到 launchd")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {task_id} 安装失败: {e}")
        return False


def setup_scheduler():
    """设置定时任务调度器"""
    logger.info("=" * 60)
    logger.info("开始设置定时任务调度器...")
    logger.info("=" * 60)

    # 创建日志目录
    os.makedirs('/Users/zhangk/workspace/Quantitative_trading/logs/scheduler', exist_ok=True)

    tasks = get_task_config()
    plist_dir = '/Users/zhangk/workspace/Quantitative_trading/backend/scheduler/launchd'
    
    installed_count = 0
    for task_id, config in tasks.items():
        if not config.get('enabled', True):
            logger.info(f"⏭️ {task_id} 已禁用，跳过")
            continue
        
        # 生成 plist 文件
        plist_content = generate_launchd_plist(task_id, config)
        plist_path = os.path.join(plist_dir, f'{task_id}.plist')
        
        with open(plist_path, 'w') as f:
            f.write(plist_content)
        
        logger.info(f"📄 生成配置文件: {plist_path}")
        
        # 安装到 launchd
        if install_launchd_plist(plist_path, task_id):
            installed_count += 1

    logger.info("=" * 60)
    logger.info(f"✅ 定时任务配置完成")
    logger.info(f"  生成配置: {len(tasks)} 个")
    logger.info(f"  安装成功: {installed_count} 个")
    logger.info("=" * 60)


if __name__ == '__main__':
    setup_scheduler()
