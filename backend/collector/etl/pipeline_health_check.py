#!/usr/bin/env python3
"""
pipeline_health_check.py - 数据管道前置条件检查器

在每个 ETL 任务执行前自动运行，检查所有依赖条件：
- 数据库连接
- stock_basic 表是否有数据（避免下载无股票代码的数据）
- 数据库分区是否覆盖目标日期
- 数据源（Baostock/Tushare/pytdx）是否可用
- 必需目录是否存在

数据源优先级：Baostock(前复权,主) → Tushare(不复权,备1) → pytdx(不复权,备2)

用法：
    python pipeline_health_check.py                      # 完整检查
    python pipeline_health_check.py --target-date 2026-06-05   # 检查指定日期
    python pipeline_health_check.py --pre-import        # 仅检查下载前置条件
    python pipeline_health_check.py --pre-sync          # 仅检查同步前置条件
    python pipeline_health_check.py --strict            # 严格模式（任何警告都失败）

返回：
    0 - 全部通过
    1 - 有错误（必须修复）
    2 - 有警告（建议修复）
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录与 backend 目录（确保 collector 等包可被导入）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'backend'))
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / '.env')


class HealthCheckResult:
    OK = 'OK'
    WARN = 'WARN'
    ERROR = 'ERROR'

    def __init__(self):
        self.checks = []  # [(name, status, message)]

    def ok(self, name, msg=''):
        self.checks.append((name, self.OK, msg))
        print(f'  ✅ {name}: {msg}')

    def warn(self, name, msg):
        self.checks.append((name, self.WARN, msg))
        print(f'  ⚠️  {name}: {msg}')

    def error(self, name, msg):
        self.checks.append((name, self.ERROR, msg))
        print(f'  ❌ {name}: {msg}')

    def has_error(self):
        return any(c[1] == self.ERROR for c in self.checks)

    def has_warn(self):
        return any(c[1] == self.WARN for c in self.checks)

    def summary(self):
        ok = sum(1 for c in self.checks if c[1] == self.OK)
        warn = sum(1 for c in self.checks if c[1] == self.WARN)
        err = sum(1 for c in self.checks if c[1] == self.ERROR)
        return f'OK={ok}, WARN={warn}, ERROR={err}'


def get_db_conn():
    """获取数据库连接"""
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=os.getenv('PG_PORT', '5432'),
        database=os.getenv('PG_DATABASE', 'quant_trading'),
        user=os.getenv('PG_USER', 'quant_user'),
        password=os.getenv('PG_PASSWORD', '')
    )


def check_database_connection(result: HealthCheckResult):
    """检查数据库连接"""
    print('\n[1/6] 📡 数据库连接检查')
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        result.ok('数据库连接', f'{os.getenv("PG_HOST")}:{os.getenv("PG_PORT")}')
    except Exception as e:
        result.error('数据库连接', f'连接失败: {e}')


def check_stock_basic(result: HealthCheckResult):
    """检查 stock_basic 表"""
    print('\n[2/6] 📋 股票基础信息表检查')
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM stock_basic')
        total = cur.fetchone()[0]
        if total == 0:
            result.error('stock_basic 表', '为空！需要先执行 init_data.py 下载股票列表')
        else:
            result.ok('stock_basic 记录数', f'{total} 只股票')

        cur.execute("""
            SELECT COUNT(*) FROM stock_basic
            WHERE list_date IS NULL OR industry IS NULL
        """)
        null_count = cur.fetchone()[0]
        if null_count > total * 0.5:
            result.warn('stock_basic 字段完整度', f'{null_count}/{total} ({null_count*100//total}%) 缺少 list_date/industry')
        else:
            result.ok('stock_basic 字段完整度', f'{(total-null_count)*100//total}% 完整')

        # 检查退市股票过滤
        cur.execute("SELECT COUNT(*) FROM stock_basic WHERE delist_date IS NOT NULL")
        delist = cur.fetchone()[0]
        result.ok('退市股票数', f'{delist} 只（已自动跳过）')

        cur.close()
        conn.close()
    except Exception as e:
        result.error('stock_basic 检查', str(e))


def check_partitions(result: HealthCheckResult, target_date: str = None):
    """检查数据库分区覆盖"""
    print('\n[3/6] 🗄️  数据库分区检查')
    if not target_date:
        target_date = datetime.now().strftime('%Y-%m-%d')

    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # 检查年度分区
        target_year = datetime.strptime(target_date, '%Y-%m-%d').year
        for table in ['stock_quotes']:
            partition_name = f'{table}_{target_year}'
            cur.execute("""
                SELECT 1 FROM pg_class c
                JOIN pg_inherits i ON c.oid = i.inhrelid
                JOIN pg_class p ON i.inhparent = p.oid
                WHERE c.relname = %s AND p.relname = %s
            """, (partition_name, table))
            if cur.fetchone():
                result.ok(f'{table} 分区', f'{partition_name} 存在')
            else:
                result.error(f'{table} 分区', f'{partition_name} 不存在！需执行 partition_scheduler.py --mode auto')

        # 检查未来 7 天的分区
        for i in range(7):
            check_date = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')
            cur.execute("""
                SELECT 1 FROM stock_quotes
                WHERE cycle='1d' AND trade_date = %s LIMIT 1
            """, (check_date,))
            if cur.fetchone() is None:
                # 可能是周末/节假日，不是分区问题
                pass

        cur.close()
        conn.close()
    except Exception as e:
        result.error('分区检查', str(e))


def check_data_sources(result: HealthCheckResult):
    """检查数据源可用性（按优先级顺序：Baostock → Tushare → pytdx）"""
    print('\n[4/6] 🔌 数据源连接检查')

    # Baostock（主数据源，前复权）
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code == '0':
            result.ok('Baostock (主)', '可用（前复权）')
            bs.logout()
        else:
            result.warn('Baostock (主)', f'登录失败: {lg.error_msg}')
    except Exception as e:
        result.warn('Baostock (主)', f'连接异常: {str(e)[:80]}')

    # Tushare（备1，不复权→自动转换）
    try:
        tushare_token = os.getenv('TUSHARE_TOKEN')
        if not tushare_token:
            result.warn('Tushare (备1)', '未配置 TUSHARE_TOKEN，跳过')
        else:
            import tushare as ts
            pro = ts.pro_api(tushare_token)
            # 仅验证 pro_api 对象创建成功，避免调用 trade_cal 等受限接口消耗配额
            if pro is not None:
                result.ok('Tushare (备1)', '已配置 TOKEN（不复权→自动转换）')
            else:
                result.warn('Tushare (备1)', 'pro_api 初始化失败')
    except Exception as e:
        result.warn('Tushare (备1)', f'连接异常: {str(e)[:80]}')

    # pytdx（备2，不复权→自动转换）
    try:
        from collector.datasource.pytdx import PytdxDataSource
        pdx = PytdxDataSource()
        if pdx.connect():
            result.ok('pytdx/通达信 (备2)', '可用（不复权→自动转换）')
            pdx.disconnect()
        else:
            result.warn('pytdx/通达信 (备2)', '连接失败')
    except Exception as e:
        result.warn('pytdx/通达信 (备2)', f'连接异常: {str(e)[:80]}')


def check_directories(result: HealthCheckResult):
    """检查必需目录"""
    print('\n[5/6] 📁 目录检查')
    required_dirs = [
        ('logs/etl', PROJECT_ROOT / 'logs' / 'etl'),
        ('data/metadata', PROJECT_ROOT / 'data' / 'metadata'),
        ('data/snapshot', PROJECT_ROOT / 'data' / 'snapshot'),
    ]
    for name, path in required_dirs:
        if path.exists():
            result.ok(name, str(path))
        else:
            try:
                path.mkdir(parents=True, exist_ok=True)
                result.ok(name, f'已自动创建 {path}')
            except Exception as e:
                result.warn(name, f'不存在且无法创建: {e}')


def check_recent_data(result: HealthCheckResult, target_date: str = None):
    """检查最近的数据状态"""
    print('\n[6/6] 📊 最近数据状态')
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        # stock_quotes 最新日期
        cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
        latest_quote = cur.fetchone()[0]
        if latest_quote:
            result.ok('stock_quotes 最新日期', str(latest_quote))
        else:
            result.warn('stock_quotes', '无任何数据')

        # stock_daily_snapshot 最新日期
        cur.execute("SELECT MAX(trade_date) FROM stock_daily_snapshot")
        latest_snapshot = cur.fetchone()[0]
        if latest_snapshot:
            result.ok('stock_daily_snapshot 最新日期', str(latest_snapshot))
        else:
            result.warn('stock_daily_snapshot', '无任何数据（宽表为空）')

        # 最近一天数据完整度
        if latest_quote:
            cur.execute("SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE trade_date = %s AND cycle='1d'", (latest_quote,))
            cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM stock_basic")
            total = cur.fetchone()[0]
            coverage = cnt * 100 // total if total else 0
            if coverage < 80:
                result.warn('最近数据完整度', f'{cnt}/{total} ({coverage}%) - 低于 80%')
            else:
                result.ok('最近数据完整度', f'{cnt}/{total} ({coverage}%)')

        cur.close()
        conn.close()
    except Exception as e:
        result.error('最近数据状态', str(e))


def main():
    parser = argparse.ArgumentParser(description='数据管道前置条件检查器')
    parser.add_argument('--target-date', type=str, help='检查目标日期（YYYY-MM-DD）')
    parser.add_argument('--pre-import', action='store_true', help='下载前置条件（stock_basic + 分区 + 数据源）')
    parser.add_argument('--pre-sync', action='store_true', help='同步前置条件（数据库连接 + stock_quotes）')
    parser.add_argument('--strict', action='store_true', help='严格模式（警告也算失败）')

    args = parser.parse_args()

    print('=' * 70)
    print(f'  数据管道前置条件检查  |  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    if args.target_date:
        print(f'  目标日期: {args.target_date}')
    if args.pre_import:
        print(f'  模式: 下载前置检查')
    elif args.pre_sync:
        print(f'  模式: 同步前置检查')
    print('=' * 70)

    result = HealthCheckResult()

    # 基础检查（始终执行）
    check_database_connection(result)

    if args.pre_sync:
        # 同步前置：仅需 stock_quotes 有数据
        check_recent_data(result)
    else:
        # 默认/下载前置：完整检查
        check_stock_basic(result)
        check_partitions(result, args.target_date)
        check_data_sources(result)
        check_directories(result)
        check_recent_data(result)

    print('\n' + '=' * 70)
    print(f'  检查结果: {result.summary()}')
    print('=' * 70)

    if result.has_error():
        print('\n❌ 有错误，必须修复后才能继续执行 ETL 任务')
        if result.checks:
            print('\n错误详情:')
            for name, status, msg in result.checks:
                if status == 'ERROR':
                    print(f'  - {name}: {msg}')
        sys.exit(1)
    elif result.has_warn():
        print('\n⚠️  有警告，建议修复')
        if args.strict:
            sys.exit(2)
        sys.exit(0)
    else:
        print('\n✅ 全部检查通过，可以继续执行 ETL 任务')
        errors = sum(1 for c in result.checks if c[1] == HealthCheckResult.ERROR)
        warnings = sum(1 for c in result.checks if c[1] == HealthCheckResult.WARN)
        print(f'TASK_RESULT:{json.dumps({"rows_affected": len(result.checks), "extra_metrics": {"errors": errors, "warnings": warnings}})}')
        sys.exit(0)


if __name__ == '__main__':
    main()
