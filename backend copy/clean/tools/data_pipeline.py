#!/usr/bin/env python3
"""
数据处理管道主入口

流程设计：
1. 数据下载阶段 → 由外部调度（如crontab）触发
2. 数据质量检查阶段 → 在下载完成后自动调用
3. 数据补全/增强阶段 → 在质量检查通过后调用

调用方式：
    # 完整流程（下载后自动执行检查和补全）
    python scripts/data_pipeline.py full
    
    # 仅执行数据质量检查
    python scripts/data_pipeline.py check
    
    # 仅执行数据补全
    python scripts/data_pipeline.py enrich
    
    # 指定日期执行
    python scripts/data_pipeline.py full --date 2026-06-01
    
    # 检查特定表
    python scripts/data_pipeline.py check --table stock_daily_snapshot
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

def run_script(script_name, args=None):
    """执行指定的脚本"""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
    
    if not os.path.exists(script_path):
        print(f"❌ 脚本不存在: {script_path}")
        return False
    
    cmd = ['python', script_path]
    if args:
        cmd.extend(args)
    
    print(f"🚀 执行: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        if result.returncode == 0:
            print(f"✅ {script_name} 执行成功")
            if result.stdout:
                print(f"输出:\n{result.stdout}")
            return True
        else:
            print(f"❌ {script_name} 执行失败")
            if result.stderr:
                print(f"错误信息:\n{result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 执行 {script_name} 时发生异常: {e}")
        return False

def run_sql_script(sql_file):
    """执行SQL脚本"""
    # 在 collector/db/sql/ 目录下查找 SQL 文件
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sql_path = os.path.join(base_dir, 'collector', 'db', 'sql', sql_file)
    
    if not os.path.exists(sql_path):
        print(f"❌ SQL文件不存在: {sql_path}")
        return False
    
    # 从环境变量获取数据库配置
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    db_host = os.getenv("PG_HOST", "localhost")
    db_port = os.getenv("PG_PORT", "5432")
    db_name = os.getenv("PG_DATABASE", "quant_trading")
    db_user = os.getenv("PG_USER", "quant_user")
    
    cmd = [
        'psql',
        '-h', db_host,
        '-p', db_port,
        '-d', db_name,
        '-U', db_user,
        '-f', sql_path
    ]
    
    print(f"🚀 执行SQL: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, 'PGPASSWORD': os.getenv("PG_PASSWORD", "")})
        
        if result.returncode == 0:
            print(f"✅ {sql_file} 执行成功")
            return True
        else:
            print(f"❌ {sql_file} 执行失败")
            if result.stderr:
                print(f"错误信息:\n{result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 执行 {sql_file} 时发生异常: {e}")
        return False

def check_data_quality(date_str=None):
    """执行数据质量检查流程"""
    print("\n" + "="*60)
    print("📊 数据质量检查阶段")
    print("="*60)
    
    checks = [
        {
            'name': '检查表结构一致性',
            'script': 'quality/check_table_schema.py',
            'critical': True
        },
        {
            'name': '检查股票基础信息',
            'script': 'quality/check_stock_basic.py',
            'critical': False
        },
        {
            'name': '检查行情数据',
            'script': 'quality/check_quotes_data.py',
            'args': [f'--date={date_str}'] if date_str else [],
            'critical': True
        },
        {
            'name': '检查数据完整性',
            'script': 'quality/check_data_quality.py',
            'critical': True
        },
        {
            'name': '检查重复数据',
            'script': 'quality/check_duplicates.py',
            'critical': False
        },
        {
            'name': '验证分钟数据',
            'script': 'quality/validate_minute_data.py',
            'critical': False
        }
    ]
    
    failed_checks = []
    for check in checks:
        print(f"\n🔍 {check['name']}")
        print("-" * 40)
        
        args = check.get('args', [])
        success = run_script(check['script'], args)
        
        if not success and check['critical']:
            failed_checks.append(check['name'])
    
    if failed_checks:
        print(f"\n❌ 以下关键检查失败: {', '.join(failed_checks)}")
        return False
    else:
        print("\n✅ 所有数据质量检查通过")
        return True

def enrich_data(date_str=None):
    """执行数据补全/增强流程"""
    print("\n" + "="*60)
    print("🔧 数据补全/增强阶段")
    print("="*60)
    
    # 确保宽表存在
    print("\n📋 确保宽表结构完整")
    run_sql_script('create_snapshot_table.sql')
    
    enrichments = [
        {
            'name': '从Parquet更新基础字段',
            'script': 'enrichment/update_from_parquet.py',
            'required': True
        },
        {
            'name': '从Parquet更新技术指标',
            'script': 'enrichment/update_indicators_from_parquet.py',
            'required': True
        },
        {
            'name': '更新特殊标志（ST/新股/涨跌停）',
            'script': 'enrichment/update_special_flags.py',
            'required': False
        },
        {
            'name': '更新地区字段',
            'script': 'enrichment/update_area_from_parquet.py',
            'required': False
        },
        {
            'name': '更新所有扩展字段',
            'script': 'enrichment/update_all_fields_from_parquet.py',
            'required': True
        },
        {
            'name': '计算20/60/120/250日新高',
            'script': 'enrichment/calculate_highs.py',
            'args': [f'--date={date_str}'] if date_str else [],
            'required': True
        }
    ]
    
    failed_enrichments = []
    for enrichment in enrichments:
        print(f"\n🔧 {enrichment['name']}")
        print("-" * 40)
        
        args = enrichment.get('args', [])
        success = run_script(enrichment['script'], args)
        
        if not success and enrichment['required']:
            failed_enrichments.append(enrichment['name'])
    
    if failed_enrichments:
        print(f"\n❌ 以下必需的补全任务失败: {', '.join(failed_enrichments)}")
        return False
    else:
        print("\n✅ 所有数据补全任务完成")
        return True

def main():
    parser = argparse.ArgumentParser(description='数据处理管道 - 统一管理数据检查和补全流程')
    parser.add_argument('action', choices=['full', 'check', 'enrich'], 
                        help='执行的操作: full(完整流程), check(仅检查), enrich(仅补全)')
    parser.add_argument('--date', type=str, 
                        help='指定处理日期（格式：YYYY-MM-DD），默认使用最新日期')
    parser.add_argument('--table', type=str, 
                        help='指定检查的表名（仅check模式有效）')
    
    args = parser.parse_args()
    
    # 设置日期
    date_str = args.date or (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print("="*60)
    print("📈 量化交易数据处理管道")
    print(f"日期: {date_str}")
    print("="*60)
    
    if args.action == 'full':
        # 完整流程：检查 → 补全
        if check_data_quality(date_str):
            enrich_data(date_str)
        else:
            print("\n❌ 数据质量检查失败，跳过数据补全")
    
    elif args.action == 'check':
        check_data_quality(date_str)
    
    elif args.action == 'enrich':
        enrich_data(date_str)

if __name__ == '__main__':
    main()
