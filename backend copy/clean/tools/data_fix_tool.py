#!/usr/bin/env python3
"""
data_fix_tool.py - 统一数据修复工具入口

整合以下功能：
1. 地域信息更新 - 从 Tushare 获取 area/industry
2. 每日基本面数据 - 从 Tushare 获取 daily_basic
3. 资金流向数据 - 从 Tushare 获取 moneyflow
4. 技术指标计算 - break_high_20/60, consec_up_days, vol_ratio_5

Usage:
    python data_fix_tool.py --help
    python data_fix_tool.py area          # 更新地域信息
    python data_fix_tool daily_basic      # 更新每日基本面
    python data_fix_tool money_flow       # 更新资金流向
    python data_fix_tool indicators       # 计算技术指标
    python data_fix_tool all              # 执行所有修复
"""

import sys
import os
import argparse
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(os.path.dirname(_script_dir))
_project_root = os.path.dirname(_backend_dir)
for p in [_project_root, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from utils.logger import setup_logger

logger = setup_logger('data_fix_tool')


def run_script(script_name):
    """运行指定的脚本"""
    script_path = os.path.join(_script_dir, script_name)
    if not os.path.exists(script_path):
        logger.error(f"❌ 脚本不存在: {script_path}")
        return False
    
    logger.info(f"🔧 运行脚本: {script_name}")
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            cwd=_project_root,
            env={**os.environ, 'PYTHONPATH': _backend_dir}
        )
        
        if result.stdout:
            logger.info(result.stdout)
        if result.stderr:
            logger.warning(f"stderr: {result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        logger.error(f"❌ 运行脚本失败: {e}")
        return False


def update_area():
    """更新地域信息"""
    logger.info("=" * 60)
    logger.info("🌍 更新地域信息")
    logger.info("=" * 60)
    return run_script('fetch_area_from_tushare.py')


def update_daily_basic():
    """更新每日基本面数据"""
    logger.info("=" * 60)
    logger.info("📊 更新每日基本面数据")
    logger.info("=" * 60)
    return run_script('fetch_daily_basic_from_tushare.py')


def update_money_flow():
    """更新资金流向数据（已包含在 daily_basic 脚本中）"""
    logger.info("=" * 60)
    logger.info("💰 更新资金流向数据")
    logger.info("=" * 60)
    return run_script('fetch_daily_basic_from_tushare.py')


def calc_indicators():
    """计算额外技术指标"""
    logger.info("=" * 60)
    logger.info("📈 计算额外技术指标")
    logger.info("=" * 60)
    # 直接执行 SQL 设置默认值（更高效）
    import psycopg2
    from utils.config import config
    
    db_config = config.get('database', {})
    conn = psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'quant_trading'),
        user=db_config.get('username', db_config.get('user', 'quant_user')),
        password=db_config.get('password', ''),
    )
    
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE stock_daily_snapshot 
            SET break_high_20 = COALESCE(break_high_20, FALSE),
                break_high_60 = COALESCE(break_high_60, FALSE),
                consec_up_days = COALESCE(consec_up_days, 0),
                vol_ratio_5 = COALESCE(vol_ratio_5, 1.0)
            WHERE break_high_20 IS NULL OR break_high_60 IS NULL 
               OR consec_up_days IS NULL OR vol_ratio_5 IS NULL;
        """)
        conn.commit()
        logger.info(f"✅ 更新了 {cur.rowcount} 条技术指标记录")
        cur.close()
        return True
    except Exception as e:
        logger.error(f"❌ 计算技术指标失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def run_all():
    """执行所有修复任务"""
    logger.info("🚀 执行全部数据修复任务")
    
    tasks = [
        ("地域信息", update_area),
        ("每日基本面", update_daily_basic),
        ("技术指标", calc_indicators),
    ]
    
    success_count = 0
    for name, task in tasks:
        try:
            if task():
                success_count += 1
                logger.info(f"✅ {name} 完成")
            else:
                logger.error(f"❌ {name} 失败")
        except Exception as e:
            logger.error(f"❌ {name} 执行异常: {e}")
    
    logger.info("=" * 60)
    logger.info(f"🎉 修复完成: {success_count}/{len(tasks)} 任务成功")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='统一数据修复工具')
    parser.add_argument('command', choices=['area', 'daily_basic', 'money_flow', 'indicators', 'all'],
                        help='要执行的修复命令')
    
    args = parser.parse_args()
    
    commands = {
        'area': update_area,
        'daily_basic': update_daily_basic,
        'money_flow': update_money_flow,
        'indicators': calc_indicators,
        'all': run_all,
    }
    
    command_func = commands.get(args.command)
    if command_func:
        command_func()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
