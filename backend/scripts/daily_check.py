#!/usr/bin/env python3
"""
daily_check.py - 每日数据管道自动化晨检脚本

执行 9 项标准化检查，涵盖基础设施、数据下载、宽表同步、数据补全、任务日志。

用法：
    python daily_check.py                          # 完整检查
    python daily_check.py --no-color               # 无颜色输出
    python daily_check.py --output /tmp/report.json # 输出 JSON 报告
    python daily_check.py --skip log_file_errors    # 跳过特定检查项
    python daily_check.py --list-checks             # 列出所有检查项

返回码：
    0 - 全部通过
    1 - 存在警告项（需关注）
    2 - 存在失败项（需人工介入）
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'backend'))
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / '.env')


# ===================== 检查项定义 =====================

ALL_CHECKS = [
    'postgres_service',
    'database_connection',
    'daily_quotes_freshness',
    'daily_quotes_volume',
    'missing_stocks',
    'weekly_quotes_freshness',
    'monthly_quotes_freshness',
    'snapshot_sync',
    'field_completeness',
    'task_run_log',
    'log_file_errors',
]

CHECK_DESCRIPTIONS = {
    'postgres_service': 'PostgreSQL 服务进程状态',
    'database_connection': '数据库连接测试',
    'daily_quotes_freshness': '日线行情最新日期新鲜度',
    'daily_quotes_volume': '日线行情每日数据量（≥4500 条）',
    'missing_stocks': '最新交易日缺失股票数',
    'weekly_quotes_freshness': '周K线最新日期新鲜度',
    'monthly_quotes_freshness': '月K线最新日期新鲜度',
    'snapshot_sync': '宽表同步状态 (stock_daily_snapshot)',
    'field_completeness': '关键字段填充率',
    'task_run_log': '最近任务执行日志',
    'log_file_errors': '日志文件错误计数',
}


class CheckResult:
    OK = 'OK'
    WARN = 'WARN'
    ERROR = 'ERROR'

    def __init__(self):
        self.checks = {}  # {name: (status, message, detail)}
        self.use_color = True

    def ok(self, name, msg, detail=''):
        self.checks[name] = (self.OK, msg, detail)
        self._print(name, self.OK, msg)

    def warn(self, name, msg, detail=''):
        self.checks[name] = (self.WARN, msg, detail)
        self._print(name, self.WARN, msg)

    def error(self, name, msg, detail=''):
        self.checks[name] = (self.ERROR, msg, detail)
        self._print(name, self.ERROR, msg)

    def _print(self, name, level, msg):
        icon = {'OK': '  \u2705', 'WARN': '  \u26a0\ufe0f ', 'ERROR': '  \u274c'}[level]
        if not self.use_color:
            icon = {'OK': '  [OK]', 'WARN': '  [WARN]', 'ERROR': '  [ERROR]'}[level]
        print(f'  {icon} {name}: {msg}')

    def has_error(self):
        return any(s == self.ERROR for s, _, _ in self.checks.values())

    def has_warn(self):
        return any(s == self.WARN for s, _, _ in self.checks.values())

    def summary(self):
        ok_count = sum(1 for s, _, _ in self.checks.values() if s == self.OK)
        warn_count = sum(1 for s, _, _ in self.checks.values() if s == self.WARN)
        err_count = sum(1 for s, _, _ in self.checks.values() if s == self.ERROR)
        return f'OK={ok_count}, WARN={warn_count}, ERROR={err_count}'

    def to_dict(self):
        return {
            'summary': {'ok': sum(1 for s, _, _ in self.checks.values() if s == self.OK),
                        'warn': sum(1 for s, _, _ in self.checks.values() if s == self.WARN),
                        'error': sum(1 for s, _, _ in self.checks.values() if s == self.ERROR)},
            'checks': {name: {'status': st, 'message': msg, 'detail': det}
                       for name, (st, msg, det) in self.checks.items()}
        }


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('PG_HOST', 'localhost'),
        port=int(os.getenv('PG_PORT', '5432')),
        database=os.getenv('PG_DATABASE', 'quant_trading'),
        user=os.getenv('PG_USER', 'quant_user'),
        password=os.getenv('PG_PASSWORD', '')
    )


# ===================== 检查函数 =====================

def check_postgres_service(result):
    """检查 PostgreSQL 服务进程状态"""
    try:
        host = os.getenv('PG_HOST', 'localhost')
        port = os.getenv('PG_PORT', '5432')
        r = subprocess.run(['pg_isready', '-h', host, '-p', str(port)],
                          capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            result.ok('postgres_service', f'pg_isready: {r.stdout.strip()}')
        else:
            result.error('postgres_service', f'pg_isready 返回非零: {r.stderr.strip()}')
    except FileNotFoundError:
        # pg_isready not found, try psql instead
        try:
            conn = get_db_conn()
            conn.close()
            result.ok('postgres_service', '通过 psql 连接验证（pg_isready 不可用）')
        except Exception as e:
            result.error('postgres_service', f'数据库连接失败: {e}')
    except Exception as e:
        result.error('postgres_service', f'检查失败: {e}')


def check_database_connection(result):
    """检查数据库连接"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        result.ok('database_connection', f'{os.getenv("PG_HOST")}:{os.getenv("PG_PORT")}/{os.getenv("PG_DATABASE")}')
    except Exception as e:
        result.error('database_connection', f'连接失败: {e}')


def check_daily_quotes_freshness(result):
    """检查日线行情最新日期新鲜度"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
        latest = cur.fetchone()[0]
        cur.close()
        conn.close()
        if latest is None:
            result.error('daily_quotes_freshness', '日线数据为空')
            return
        days_ago = (datetime.now().date() - latest).days
        if days_ago > 5:
            result.error('daily_quotes_freshness', f'最新交易日 {latest}，距今 {days_ago} 天（超过阈值 5 天）')
        elif days_ago > 3:
            result.warn('daily_quotes_freshness', f'最新交易日 {latest}，距今 {days_ago} 天（超过阈值 3 天）')
        else:
            result.ok('daily_quotes_freshness', f'最新交易日 {latest}')
    except Exception as e:
        result.error('daily_quotes_freshness', str(e))


def check_daily_quotes_volume(result):
    """检查日线行情每日数据量"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
        latest = cur.fetchone()[0]
        if latest is None:
            result.error('daily_quotes_volume', '日线数据为空')
            cur.close()
            conn.close()
            return
        cur.execute("SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE trade_date = %s AND cycle='1d'", (latest,))
        cnt = cur.fetchone()[0]
        cur.close()
        conn.close()
        if cnt < 4500:
            result.error('daily_quotes_volume', f'最新交易日 {latest} 仅 {cnt} 只（低于阈值 4500）')
        elif cnt < 5000:
            result.warn('daily_quotes_volume', f'最新交易日 {latest} 共 {cnt} 只（低于 5000）')
        else:
            result.ok('daily_quotes_volume', f'最新交易日 {latest} 共 {cnt} 只')
    except Exception as e:
        result.error('daily_quotes_volume', str(e))


def check_missing_stocks(result):
    """检查最新交易日缺失股票数"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
        latest = cur.fetchone()[0]
        if latest is None:
            result.warn('missing_stocks', '日线数据为空，无法计算缺失股票')
            cur.close()
            conn.close()
            return
        # 排除北交所（8/920 开头），与日线导入逻辑保持一致，
        # 避免北交所股票被误计为"缺失"产生误报
        cur.execute("""
            SELECT COUNT(*) FROM stock_basic
            WHERE (delist_date IS NULL OR delist_date > %s)
            AND code NOT LIKE '8%%'
            AND code NOT LIKE '920%%'
        """, (latest,))
        total_active = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(DISTINCT code) FROM stock_quotes
            WHERE trade_date = %s AND cycle='1d'
            AND code NOT LIKE '8%%'
            AND code NOT LIKE '920%%'
        """, (latest,))
        have_data = cur.fetchone()[0]
        cur.close()
        conn.close()
        missing = total_active - have_data
        if missing > 100:
            result.warn('missing_stocks', f'最新交易日 {latest} 缺失 {missing} 只（活跃 {total_active}，有数据 {have_data}）')
        else:
            result.ok('missing_stocks', f'最新交易日 {latest} 缺失 {missing} 只（活跃 {total_active}，有数据 {have_data}）')
    except Exception as e:
        result.warn('missing_stocks', str(e))


def check_weekly_quotes_freshness(result):
    """检查周K线最新日期新鲜度"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1w'")
        latest = cur.fetchone()[0]
        if latest is None:
            result.warn('weekly_quotes_freshness', '周K线数据为空')
            cur.close()
            conn.close()
            return
        cur.execute("SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE trade_date = %s AND cycle='1w'", (latest,))
        cnt = cur.fetchone()[0]
        cur.close()
        conn.close()
        days_ago = (datetime.now().date() - latest).days
        # 周K线阈值：超过 14 天（2周）告警
        if days_ago > 14:
            result.error('weekly_quotes_freshness', f'最新 {latest}，距今 {days_ago} 天（超过阈值 14 天），覆盖 {cnt} 只')
        elif days_ago > 7:
            result.warn('weekly_quotes_freshness', f'最新 {latest}，距今 {days_ago} 天（超过 7 天），覆盖 {cnt} 只')
        else:
            result.ok('weekly_quotes_freshness', f'最新 {latest}，覆盖 {cnt} 只')
    except Exception as e:
        result.warn('weekly_quotes_freshness', str(e))


def check_monthly_quotes_freshness(result):
    """检查月K线最新日期新鲜度"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1m'")
        latest = cur.fetchone()[0]
        if latest is None:
            result.warn('monthly_quotes_freshness', '月K线数据为空')
            cur.close()
            conn.close()
            return
        cur.execute("SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE trade_date = %s AND cycle='1m'", (latest,))
        cnt = cur.fetchone()[0]
        cur.close()
        conn.close()
        days_ago = (datetime.now().date() - latest).days
        # 月K线阈值：超过 45 天（跨月）告警
        if days_ago > 45:
            result.error('monthly_quotes_freshness', f'最新 {latest}，距今 {days_ago} 天（超过阈值 45 天），覆盖 {cnt} 只')
        elif days_ago > 31:
            result.warn('monthly_quotes_freshness', f'最新 {latest}，距今 {days_ago} 天（超过 31 天），覆盖 {cnt} 只')
        else:
            result.ok('monthly_quotes_freshness', f'最新 {latest}，覆盖 {cnt} 只')
    except Exception as e:
        result.warn('monthly_quotes_freshness', str(e))


def check_snapshot_sync(result):
    """检查宽表同步状态"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) FROM stock_daily_snapshot")
        latest = cur.fetchone()[0]
        if latest is None:
            result.error('snapshot_sync', 'stock_daily_snapshot 为空')
            cur.close()
            conn.close()
            return
        cur.execute("SELECT COUNT(*) FROM stock_daily_snapshot WHERE trade_date = %s", (latest,))
        cnt = cur.fetchone()[0]
        cur.close()
        conn.close()
        # 与日线最新日期对比
        conn2 = get_db_conn()
        cur2 = conn2.cursor()
        cur2.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d'")
        latest_quote = cur2.fetchone()[0]
        cur2.close()
        conn2.close()
        if latest_quote and latest < latest_quote:
            result.warn('snapshot_sync', f'宽表最新 {latest}（{cnt} 条），落后于日线 {latest_quote}，需同步')
        else:
            result.ok('snapshot_sync', f'最新 {latest}，共 {cnt} 条')
    except Exception as e:
        result.error('snapshot_sync', str(e))


def check_field_completeness(result):
    """检查关键字段填充率"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # 技术指标字段
        cur.execute("""
            SELECT 
              COUNT(*) as total,
              ROUND(SUM(CASE WHEN dif IS NOT NULL AND dif != 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as dif_pct,
              ROUND(SUM(CASE WHEN dea IS NOT NULL AND dea != 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as dea_pct,
              ROUND(SUM(CASE WHEN rsi6 IS NOT NULL AND rsi6 != 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as rsi6_pct
            FROM stock_indicators 
            WHERE trade_date = (SELECT MAX(trade_date) FROM stock_indicators WHERE cycle='1d') AND cycle='1d'
        """)
        row = cur.fetchone()
        total, dif_pct, dea_pct, rsi6_pct = row
        cur.close()
        conn.close()
        fields = {'dif': dif_pct, 'dea': dea_pct, 'rsi6': rsi6_pct}
        # 检查是否所有字段 ≥ 95%
        all_ok = all(v >= 95 for v in fields.values())
        if all_ok:
            result.ok('field_completeness', f'技术指标字段填充率 ≥ 95%（{total} 条）')
        else:
            low = {k: v for k, v in fields.items() if v < 95}
            result.warn('field_completeness', f'字段填充率不足: {low}')
    except Exception as e:
        result.warn('field_completeness', str(e))


def check_task_run_log(result):
    """检查最近任务执行日志"""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT task_name, status, error_message, data_date
            FROM task_run_log
            WHERE data_date >= (CURRENT_DATE - INTERVAL '3 days')
              AND status != 'success'
            ORDER BY data_date DESC, task_name
        """)
        failed = cur.fetchall()
        cur.close()
        conn.close()
        if failed:
            msg = '; '.join([f'{row[3]} {row[0]}: {row[1]}' for row in failed[:5]])
            if len(failed) > 5:
                msg += f' (共 {len(failed)} 条失败)'
            result.warn('task_run_log', f'最近 3 天有 {len(failed)} 个失败任务', msg)
        else:
            result.ok('task_run_log', '最近 3 天无失败任务')
    except Exception as e:
        result.warn('task_run_log', str(e))


def check_log_file_errors(result):
    """检查日志文件错误计数"""
    log_dirs = [
        PROJECT_ROOT / 'logs' / 'etl',
        PROJECT_ROOT / 'logs' / 'cron',
    ]
    total_errors = 0
    error_details = []
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for log_file in sorted(log_dir.glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
            try:
                with open(log_file, 'r', errors='ignore') as f:
                    for line in f:
                        if 'ERROR' in line or 'CRITICAL' in line:
                            total_errors += 1
                            if len(error_details) < 5:
                                error_details.append(f'{log_file.name}: {line.strip()[:120]}')
            except Exception:
                continue
    if total_errors > 100:
        result.warn('log_file_errors', f'日志文件中发现 {total_errors} 条 ERROR/CRITICAL')
    elif total_errors > 0:
        result.ok('log_file_errors', f'日志文件中发现 {total_errors} 条 ERROR/CRITICAL（少量，可接受）')
    else:
        result.ok('log_file_errors', '日志文件中无 ERROR/CRITICAL')


# ===================== 检查调度 =====================

CHECK_FUNCTIONS = {
    'postgres_service': check_postgres_service,
    'database_connection': check_database_connection,
    'daily_quotes_freshness': check_daily_quotes_freshness,
    'daily_quotes_volume': check_daily_quotes_volume,
    'missing_stocks': check_missing_stocks,
    'weekly_quotes_freshness': check_weekly_quotes_freshness,
    'monthly_quotes_freshness': check_monthly_quotes_freshness,
    'snapshot_sync': check_snapshot_sync,
    'field_completeness': check_field_completeness,
    'task_run_log': check_task_run_log,
    'log_file_errors': check_log_file_errors,
}


def main():
    parser = argparse.ArgumentParser(description='每日数据管道自动化晨检脚本')
    parser.add_argument('--no-color', action='store_true', help='禁用颜色输出')
    parser.add_argument('--output', type=str, help='输出 JSON 报告到文件')
    parser.add_argument('--skip', type=str, action='append', help='跳过指定检查项')
    parser.add_argument('--list-checks', action='store_true', help='列出所有检查项')
    args = parser.parse_args()

    # 列出检查项
    if args.list_checks:
        print('可用检查项:')
        for name in ALL_CHECKS:
            desc = CHECK_DESCRIPTIONS.get(name, '')
            print(f'  {name:30s} {desc}')
        sys.exit(0)

    result = CheckResult()
    result.use_color = not args.no_color

    skipped = set(args.skip or [])

    print('=' * 70)
    print(f'  每日数据管道晨检  |  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70)

    for name in ALL_CHECKS:
        if name in skipped:
            print(f'  \u23ed {name}: 已跳过')
            continue
        print(f'\n[{name}] {CHECK_DESCRIPTIONS.get(name, "")}')
        CHECK_FUNCTIONS[name](result)

    print('\n' + '=' * 70)
    print(f'  检查结果: {result.summary()}')
    print('=' * 70)

    if result.has_error():
        print('\n\u274c 有失败项，需人工介入')
        for name, (st, msg, det) in result.checks.items():
            if st == 'ERROR':
                print(f'  - {name}: {msg}')
        exit_code = 2
    elif result.has_warn():
        print('\n\u26a0\ufe0f  有警告项，需关注')
        exit_code = 1
    else:
        print('\n\u2705 全部检查通过')
        exit_code = 0

    # 输出 JSON 报告
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report = result.to_dict()
        report['timestamp'] = datetime.now().isoformat()
        report['exit_code'] = exit_code
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n\u2705 JSON 报告已保存到: {output_path}')

    # 打印 TASK_RESULT（兼容 daily_job_runner 解析）
    report = result.to_dict()
    report['exit_code'] = exit_code
    print(f'TASK_RESULT:{json.dumps(report, ensure_ascii=False)}')

    sys.exit(exit_code)


if __name__ == '__main__':
    main()