#!/usr/bin/env python3
"""
health_monitor.py - 数据管道心跳守护进程

监控 import_daily_data（下载）、daily_snapshot_sync（清洗）、run_data_complete（补全）
每分钟输出一行结构化心跳日志，包含进程状态、工作进度、数据库快照。

用法:
    python health_monitor.py --daemon      # 常驻后台模式（推荐）
    python health_monitor.py --once        # 单次检查模式
"""

import os
import sys
import time
import re
import subprocess
import argparse
from datetime import datetime

# 项目根目录: .../backend/collector/etl → 向上4层到项目根
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'backend'))

PROJECT_ROOT = _PROJECT_ROOT
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
HEARTBEAT_LOG = os.path.join(LOG_DIR, 'heartbeat.log')

# 监控目标定义
MONITORED_TASKS = {
    'download': {
        'script_pattern': 'import_daily_data.py',
        'log_file': os.path.join(LOG_DIR, 'daily_import.log'),
        'label': '下载',
    },
    'clean': {
        # 项目根目录下的 sync_quotes_to_snapshot.py（旧 daily_snapshot_sync.py 已废弃）
        'script_pattern': 'sync_quotes_to_snapshot.py',
        'log_file': os.path.join(LOG_DIR, 'daily_sync.log'),
        'label': '清洗',
    },
    'complete': {
        'script_pattern': 'run_data_complete.py',
        'log_file': os.path.join(LOG_DIR, 'data_complementer.log'),
        'label': '补全',
    },
}


def ensure_log_dir():
    """确保日志目录存在"""
    os.makedirs(LOG_DIR, exist_ok=True)


def check_process(script_pattern: str) -> dict:
    """检查进程是否存活，返回状态和PID"""
    try:
        # pgrep -f 匹配脚本名
        result = subprocess.run(
            ['pgrep', '-f', script_pattern],
            capture_output=True, text=True, timeout=5
        )
        pids = [p.strip() for p in result.stdout.split('\n') if p.strip()]
        # 过滤掉当前进程自己（health_monitor.py 可能也匹配到）
        pids = [p for p in pids if p != str(os.getpid())]
        if pids:
            # 取最旧的进程（最先启动的）
            return {'alive': True, 'pid': pids[0], 'count': len(pids)}
        return {'alive': False, 'pid': None, 'count': 0}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {'alive': False, 'pid': None, 'count': 0, 'error': 'pgrep失败'}


def tail_log(log_path: str, max_lines: int = 5) -> list:
    """读取日志文件最后几行（纯Python实现，避免subprocess缓冲问题）"""
    try:
        if not os.path.exists(log_path):
            return []
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return [line.strip() for line in lines[-max_lines:] if line.strip()]
    except Exception:
        return []


def extract_progress_from_log(lines: list, task_name: str) -> str:
    """从日志行中提取进度信息（从最新行往前扫描，找到信息最丰富的行）"""
    if not lines:
        return '无日志'

    def find_matching_line(pattern):
        """从后往前找第一个匹配的行"""
        for line in reversed(lines):
            m = re.search(pattern, line)
            if m:
                return m
        return None

    # 下载进度: 优先找 progress 行，再找完成行
    if task_name == 'download':
        m = find_matching_line(r'\[(\d+)/(\d+)\]\s*增量导入\s+([\w.]+)')
        if m:
            current, total, code = m.groups()
            pct = int(current) * 100 // int(total)
            return f'{current}/{total}({pct}%) {code}'
        m = find_matching_line(r'增量导入完成.*')
        if m:
            return m.group(0)

    # 清洗进度
    if task_name == 'clean':
        m = find_matching_line(r'宽表同步完成.*|开始同步.*')
        if m:
            return m.group(0)

    # 补全进度
    if task_name == 'complete':
        m = find_matching_line(r'同步完成.*|数据补全.*|计算完成.*')
        if m:
            return m.group(0)

    # 兜底: 取最后一行前80字符
    last = lines[-1]
    return last[:80] + '...' if len(last) > 80 else last


def query_db_snapshot() -> dict:
    """查询数据库当前快照"""
    snapshot = {'stock_quotes': {}, 'stock_daily_snapshot': {}, 'error': None}
    try:
        # psql 命令路径（兼容不同安装位置）
        psql_path = '/usr/local/opt/postgresql@18/bin/psql'
        if not os.path.exists(psql_path):
            psql_path = '/usr/bin/psql'
        if not os.path.exists(psql_path):
            psql_path = 'psql'  # 最后尝试 PATH 中的 psql

        # 使用子进程执行简短 SQL 查询，避免长连接
        sql = """
            SELECT 'stock_quotes' as tbl, trade_date, COUNT(*) as cnt
            FROM stock_quotes WHERE cycle='1d' AND trade_date >= CURRENT_DATE - INTERVAL '3 days'
            GROUP BY trade_date ORDER BY trade_date DESC LIMIT 3;
        """
        result = subprocess.run(
            [
                psql_path, '-h', 'localhost', '-p', '5432',
                '-d', 'quant_trading', '-U', 'quant_user',
                '-t', '-A', '-F', '|',
                '-c', sql
            ],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, 'PGPASSWORD': os.environ.get('PG_PASSWORD', '990518')}
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 3:
                    snapshot['stock_quotes'][parts[1].strip()] = int(parts[2].strip())

        # stock_daily_snapshot 最近数据
        sql2 = """
            SELECT trade_date, COUNT(*) FROM stock_daily_snapshot
            WHERE trade_date >= CURRENT_DATE - INTERVAL '3 days'
            GROUP BY trade_date ORDER BY trade_date DESC LIMIT 3;
        """
        result2 = subprocess.run(
            [
                psql_path, '-h', 'localhost', '-p', '5432',
                '-d', 'quant_trading', '-U', 'quant_user',
                '-t', '-A', '-F', '|',
                '-c', sql2
            ],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, 'PGPASSWORD': os.environ.get('PG_PASSWORD', '990518')}
        )
        if result2.returncode == 0 and result2.stdout.strip():
            for line in result2.stdout.strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 2:
                    snapshot['stock_daily_snapshot'][parts[0].strip()] = int(parts[1].strip())

    except Exception as e:
        snapshot['error'] = str(e)

    return snapshot


def format_db_snapshot(snapshot: dict) -> str:
    """格式化数据库快照为紧凑字符串"""
    parts = []
    if snapshot.get('stock_quotes'):
        dates = sorted(snapshot['stock_quotes'].keys(), reverse=True)
        q_str = 'q:' + '|'.join(f'{d[-5:]}({snapshot["stock_quotes"][d]})' for d in dates[:2])
        parts.append(q_str)
    if snapshot.get('stock_daily_snapshot'):
        dates = sorted(snapshot['stock_daily_snapshot'].keys(), reverse=True)
        s_str = 'sn:' + '|'.join(f'{d[-5:]}({snapshot["stock_daily_snapshot"][d]})' for d in dates[:2])
        parts.append(s_str)
    if snapshot.get('error'):
        parts.append(f'ERR:{snapshot["error"][:30]}')
    return ' '.join(parts) if parts else 'no_data'


def get_memory_usage() -> str:
    """获取系统内存使用率"""
    try:
        if sys.platform == 'darwin':
            result = subprocess.run(
                ['vm_stat'],
                capture_output=True, text=True, timeout=5
            )
            # 简单解析
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return 'ok'
        return ''
    except Exception:
        return ''


def collect_status() -> dict:
    """采集所有监控对象的当前状态"""
    status = {
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'tasks': {},
        'db': query_db_snapshot(),
    }

    for task_name, task_cfg in MONITORED_TASKS.items():
        proc = check_process(task_cfg['script_pattern'])
        log_lines = tail_log(task_cfg['log_file'])
        progress = extract_progress_from_log(log_lines, task_name)

        status['tasks'][task_name] = {
            'alive': proc['alive'],
            'pid': proc['pid'],
            'progress': progress,
            'label': task_cfg['label'],
        }

    return status


def format_heartbeat(status: dict) -> str:
    """格式化为用户易读的心跳日志（多行，每行一个环节）

    格式示例:
        07:21:51，下载，正常，1574/4876(32%)，处理到 SZ.002808
        07:21:51，清洗，空闲，-，-
        07:21:51，补全，空闲，-，-
        07:21:51，DB，q:06-04(1423)|06-03(4543) sn:06-04(93)|06-03(4543)
    """
    timestamp = status['timestamp']
    lines = []

    for task_name in ['download', 'clean', 'complete']:
        t = status['tasks'][task_name]
        label = t['label']  # 下载/清洗/补全

        if t['alive']:
            prog = t['progress']
            if '完成' in prog and ('成功' in prog or '完成' in prog):
                state = '完成'
            elif '无日志' in prog:
                state = '工作中'
            else:
                state = '正常'

            progress_str, current_item = _parse_progress(t['progress'])
        else:
            state = '空闲'
            progress_str, current_item = '-', '-'

        item_part = f'，处理到 {current_item}' if current_item and current_item != '-' else '，-'
        lines.append(f'{timestamp}，{label}，{state}，{progress_str}{item_part}')

    # DB 快照
    db_str = format_db_snapshot(status['db'])
    lines.append(f'{timestamp}，DB，{db_str}')

    return '\n'.join(lines)


def _parse_progress(progress: str) -> tuple:
    """解析进度文本为 (进度概要, 当前处理项)"""
    if not progress or progress == '无日志':
        return '-', '-'

    # 下载: "1420/4876(29%) SZ.002808" 或 "增量导入完成: 成功 4538, 失败 339"
    m = re.search(r'(\d+)/(\d+)\((\d+)%\)\s+([\w.]+)', progress)
    if m:
        current, total, pct, code = m.groups()
        return f'{current}/{total}({pct}%)', code

    m = re.search(r'增量导入完成.*', progress)
    if m:
        return m.group(0)[:60], '-'

    # 清洗: "开始同步 2026-06-04"
    m = re.search(r'开始同步\s*([\d-]+)', progress)
    if m:
        return m.group(0)[:30], m.group(1)

    m = re.search(r'宽表同步完成.*', progress)
    if m:
        return m.group(0)[:40], '-'

    # 补全
    m = re.search(r'同步完成.*|数据补全.*|计算完成.*', progress)
    if m:
        return m.group(0)[:40], '-'

    # 兜底
    return progress[:50], '-'


def detect_stall(current: dict, previous: dict) -> bool:
    """检测是否连续停滞：比较两轮 DB 快照是否有变化"""
    if previous is None:
        return False

    # 只看 download 任务
    if current['tasks']['download']['alive'] and previous['tasks']['download']['alive']:
        # 比较 db 中最新日期的记录数
        curr_q = current['db'].get('stock_quotes', {})
        prev_q = previous['db'].get('stock_quotes', {})
        if curr_q == prev_q:
            return True
    return False


def daemon_loop(interval: int = 60):
    """常驻循环"""
    ensure_log_dir()
    previous_status = None
    stall_count = 0
    current_interval = interval

    # 写入一条启动标记
    with open(HEARTBEAT_LOG, 'a') as f:
        f.write(f"\n=== HEALTH MONITOR STARTED at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    STALL_THRESHOLD = 3  # 连续几次无变化视为停滞

    while True:
        try:
            status = collect_status()
            heartbeat_line = format_heartbeat(status)

            # 停滞检测
            is_stalled = detect_stall(status, previous_status)
            if is_stalled and status['tasks']['download']['alive']:
                stall_count += 1
            else:
                stall_count = 0

            # 输出心跳日志
            with open(HEARTBEAT_LOG, 'a') as f:
                f.write(heartbeat_line + '\n')

            # 打印到 stdout（便于 nohup 查看）
            print(heartbeat_line, flush=True)

            # 停滞告警
            if stall_count >= STALL_THRESHOLD:
                alert = f"[ALERT] {status['timestamp']} 下载停滞 {stall_count} 次检查，无数据增长!"
                with open(HEARTBEAT_LOG, 'a') as f:
                    f.write(alert + '\n')
                print(alert, flush=True)
                current_interval = 30  # 加速检查
            else:
                current_interval = interval

            previous_status = status
            time.sleep(current_interval)

        except KeyboardInterrupt:
            print("\nHEALTH MONITOR STOPPED", flush=True)
            break
        except Exception as e:
            error_line = f"[ERR] {datetime.now().strftime('%H:%M:%S')} health_monitor异常: {e}"
            with open(HEARTBEAT_LOG, 'a') as f:
                f.write(error_line + '\n')
            print(error_line, flush=True)
            time.sleep(interval)


def run_once():
    """单次检查模式"""
    ensure_log_dir()
    status = collect_status()
    line = format_heartbeat(status)
    with open(HEARTBEAT_LOG, 'a') as f:
        f.write(line + '\n')
    print(line)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='数据管道心跳守护进程')
    parser.add_argument('--daemon', action='store_true', help='常驻后台模式（每分钟检查一次）')
    parser.add_argument('--once', action='store_true', help='单次检查模式')
    parser.add_argument('--interval', type=int, default=60, help='检查间隔（秒），默认60')
    args = parser.parse_args()

    if args.daemon:
        daemon_loop(args.interval)
    elif args.once:
        run_once()
    else:
        parser.print_help()