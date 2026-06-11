#!/usr/bin/env python3
"""
quant_trading.py - 量化交易系统统一入口

项目结构概览：
├── backend/
│   ├── clean/           # 数据清洗工具
│   │   ├── tools/       # 数据修复脚本
│   │   ├── etl/         # ETL流程
│   │   ├── enrich/      # 数据增强
│   │   ├── processor/   # 数据处理器
│   │   └── quality/     # 数据质量检查
│   ├── collector/       # 数据采集器
│   │   ├── datasource/  # 数据源接口
│   │   ├── db/          # 数据库操作
│   │   ├── etl/         # ETL调度
│   │   └── scheduler/   # 任务调度
│   └── core/            # 核心模块
│       └── api/         # API服务

Usage:
    python quant_trading.py --help
    python quant_trading.py fix area          # 修复地域信息
    python quant_trading.py fix all           # 执行所有修复
    python quant_trading.py api start         # 启动API服务
    python quant_trading.py quality check     # 数据质量检查
    python quant_trading.py collector sync    # 同步数据
"""

import sys
import os
import argparse
import subprocess

_project_root = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.join(_project_root, 'backend')
sys.path.insert(0, _backend_dir)


def run_command(cmd, cwd=None, env=None):
    """运行命令"""
    if cwd is None:
        cwd = _project_root
    if env is None:
        env = os.environ.copy()
        env['PYTHONPATH'] = _backend_dir
    
    print(f"🔧 执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"⚠️ stderr: {result.stderr}")
    
    return result.returncode == 0


def cmd_fix(args):
    """数据修复命令"""
    fix_tool = os.path.join(_backend_dir, 'clean/tools/data_fix_tool.py')
    
    if args.task == 'all':
        return run_command([sys.executable, fix_tool, 'all'])
    elif args.task == 'area':
        return run_command([sys.executable, fix_tool, 'area'])
    elif args.task == 'daily_basic':
        return run_command([sys.executable, fix_tool, 'daily_basic'])
    elif args.task == 'indicators':
        return run_command([sys.executable, fix_tool, 'indicators'])
    else:
        print(f"❌ 未知任务: {args.task}")
        return False


def cmd_api(args):
    """API服务命令"""
    if args.action == 'start':
        print("🚀 启动API服务...")
        cmd = [
            sys.executable, '-m', 'uvicorn', 'core.api.main:app',
            '--host', '0.0.0.0', '--port', '8000', '--reload'
        ]
        # 非阻塞运行
        subprocess.Popen(cmd, cwd=_project_root, env={**os.environ, 'PYTHONPATH': _backend_dir})
        print("✅ API服务已启动: http://localhost:8000")
        return True
    else:
        print(f"❌ 未知操作: {args.action}")
        return False


def cmd_quality(args):
    """数据质量检查命令"""
    if args.action == 'check':
        quality_checker = os.path.join(_backend_dir, 'clean/quality/check_data_quality.py')
        return run_command([sys.executable, quality_checker])
    else:
        print(f"❌ 未知操作: {args.action}")
        return False


def cmd_collector(args):
    """数据采集命令"""
    if args.action == 'sync':
        sync_script = os.path.join(_backend_dir, 'collector/etl/daily_snapshot_sync.py')
        return run_command([sys.executable, sync_script])
    elif args.action == 'import':
        import_script = os.path.join(_backend_dir, 'collector/etl/import_daily_data.py')
        return run_command([sys.executable, import_script])
    else:
        print(f"❌ 未知操作: {args.action}")
        return False


def cmd_status(args):
    """系统状态检查"""
    print("📊 系统状态检查")
    print("=" * 50)
    
    # 检查数据库连接
    try:
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
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stock_basic;")
        count = cur.fetchone()[0]
        print(f"✅ 数据库连接正常 - 股票数量: {count}")
        conn.close()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
    
    # 检查API服务状态
    import urllib.request
    try:
        response = urllib.request.urlopen('http://localhost:8000/api/health', timeout=2)
        if response.status == 200:
            print("✅ API服务运行正常")
    except:
        print("⚠️ API服务未运行")


def main():
    parser = argparse.ArgumentParser(description='量化交易系统统一入口',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="""

项目模块说明:
├── fix        - 数据修复工具
│   ├── area       更新地域信息
│   ├── daily_basic 更新每日基本面
│   ├── indicators 计算技术指标
│   └── all        执行所有修复
├── api        - API服务管理
│   └── start      启动API服务
├── quality    - 数据质量检查
│   └── check      执行数据质量检查
├── collector  - 数据采集
│   ├── sync       同步快照数据
│   └── import     导入日数据
└── status     - 系统状态检查

示例:
    python quant_trading.py fix all
    python quant_trading.py api start
    python quant_trading.py status
""")
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # fix 命令
    fix_parser = subparsers.add_parser('fix', help='数据修复')
    fix_parser.add_argument('task', choices=['area', 'daily_basic', 'indicators', 'all'],
                           help='修复任务')
    fix_parser.set_defaults(func=cmd_fix)
    
    # api 命令
    api_parser = subparsers.add_parser('api', help='API服务')
    api_parser.add_argument('action', choices=['start'], help='操作')
    api_parser.set_defaults(func=cmd_api)
    
    # quality 命令
    quality_parser = subparsers.add_parser('quality', help='数据质量')
    quality_parser.add_argument('action', choices=['check'], help='操作')
    quality_parser.set_defaults(func=cmd_quality)
    
    # collector 命令
    collector_parser = subparsers.add_parser('collector', help='数据采集')
    collector_parser.add_argument('action', choices=['sync', 'import'], help='操作')
    collector_parser.set_defaults(func=cmd_collector)
    
    # status 命令
    status_parser = subparsers.add_parser('status', help='系统状态')
    status_parser.set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
