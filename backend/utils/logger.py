#!/usr/bin/env python3
"""
日志工具模块 - 支持日志轮转功能

参数契约:
    rotation_mode: size/time  - 轮转策略（按体积/按时间）
    max_bytes_mb: int         - 单文件体积上限（MB），仅size模式生效
    backup_count: int          - 保留的历史文件数量
    time_interval: hourly/daily/weekly - 时间轮转周期，仅time模式生效
    compress_archived: bool    - 是否对轮转出的旧文件执行gzip压缩
    log_encoding: string      - 日志写入编码格式
    flush_interval_ms: int     - 缓冲刷新周期
"""
import gzip
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


LOG_CONFIG_DEFAULTS = {
    'rotation_mode': 'size',
    'max_bytes_mb': 50,
    'backup_count': 5,
    'time_interval': 'daily',
    'compress_archived': True,
    'log_encoding': 'utf-8',
    'flush_interval_ms': 2000,
}

# ==================== 统一日志格式（全项目一致） ====================
# 字段规范：timestamp(ISO8601 毫秒+时区) - LEVEL - logger(记录器名/模块名) - thread - message
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(name)s - %(threadName)s - %(message)s'


class IsoFormatter(logging.Formatter):
    """统一日志格式化器：将 asctime 输出为 ISO8601 时间戳（毫秒 + 时区，如 2026-08-27T17:40:38.123+08:00）。"""

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        dt = datetime.fromtimestamp(record.created).astimezone()
        return dt.isoformat(timespec='milliseconds')


class GzipRotator:
    """日志轮转后自动压缩处理器"""

    def __call__(self, source: str, dest: str):
        """轮转时压缩旧日志文件"""
        with open(source, 'rb') as f_in:
            with gzip.open(dest, 'wb') as f_out:
                f_out.writelines(f_in)
        os.remove(source)


class MultiProcessProtectionHandler(logging.FileHandler):
    """支持多进程PID检测的文件处理器"""

    def __init__(self, filename, mode='a', encoding=None, delay=False):
        self.pid_file = f"{filename}.pid"
        self.check_pid_consistency()
        super().__init__(filename, mode, encoding, delay)

    def check_pid_consistency(self):
        """检查是否有多进程冲突"""
        if os.path.exists(self.pid_file):
            with open(self.pid_file, 'r') as f:
                old_pid = f.read().strip()
            if old_pid and old_pid != str(os.getpid()):
                current_pid = os.getpid()
                print(f"WARNING: Detected PID conflict. Old: {old_pid}, Current: {current_pid}",
                      file=sys.stderr)
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))

    def emit(self, record):
        try:
            super().emit(record)
        except Exception:
            self.handleError(record)


def setup_logger(
    name: str,
    rotation_mode: str = None,
    max_bytes_mb: int = None,
    backup_count: int = None,
    time_interval: str = None,
    compress_archived: bool = None,
    log_dir: str = None,
    level: int = logging.INFO,
    filename: str = None
) -> logging.Logger:
    """
    设置日志记录器，支持日志轮转功能

    Args:
        name: 日志记录器名称
        rotation_mode: 轮转模式 ('size' 或 'time')
        max_bytes_mb: 单文件最大体积(MB)，仅size模式
        backup_count: 保留的历史文件数量
        time_interval: 时间轮转周期 ('hourly', 'daily', 'weekly')
        compress_archived: 是否压缩历史日志
        log_dir: 日志目录路径（支持环境变量或绝对路径）
        level: 日志级别
        filename: 自定义日志文件名（如带日期的"indicator_compute_20260909.log"），
            缺省使用 f"{name}.log"，便于按日期生成每日文件避免单文件过大

    Returns:
        配置好的logger实例
    """
    rotation_mode = rotation_mode or LOG_CONFIG_DEFAULTS['rotation_mode']
    max_bytes_mb = max_bytes_mb or LOG_CONFIG_DEFAULTS['max_bytes_mb']
    backup_count = backup_count or LOG_CONFIG_DEFAULTS['backup_count']
    time_interval = time_interval or LOG_CONFIG_DEFAULTS['time_interval']
    compress_archived = compress_archived if compress_archived is not None else LOG_CONFIG_DEFAULTS['compress_archived']
    log_dir = log_dir or os.environ.get('LOG_DIR', 'logs')

    os.makedirs(log_dir, exist_ok=True)
    try:
        os.chmod(log_dir, 0o755)
    except PermissionError:
        pass

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = IsoFormatter(LOG_FORMAT)
    console_handler.setFormatter(console_formatter)

    log_file = os.path.join(log_dir, filename or f"{name}.log")

    if rotation_mode == 'size':
        max_bytes = max_bytes_mb * 1024 * 1024
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=LOG_CONFIG_DEFAULTS['log_encoding'],
            delay=True
        )
        if compress_archived:
            file_handler.rotator = GzipRotator()
    else:
        when, interval = _parse_time_interval(time_interval)
        file_handler = TimedRotatingFileHandler(
            log_file,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding=LOG_CONFIG_DEFAULTS['log_encoding'],
            delay=True
        )
        if compress_archived:
            file_handler.rotator = GzipRotator()

    file_handler.setLevel(level)
    file_formatter = IsoFormatter(LOG_FORMAT)
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def _parse_time_interval(interval: str) -> tuple:
    """
    解析时间轮转周期配置

    Args:
        interval: 时间字符串 ('hourly', 'daily', 'weekly')

    Returns:
        tuple: (when, interval) for TimedRotatingFileHandler
    """
    interval_map = {
        'hourly': ('H', 1),
        'daily': ('midnight', 1),
        'weekly': ('W6', 1),
    }
    return interval_map.get(interval, ('midnight', 1))


def setup_detail_and_summary_loggers(
    name: str,
    level: int = logging.INFO,
) -> tuple:
    """创建「明细/汇总」分离的双 logger（日志治理）。

    设计背景（见 .trae/rules/量化交易.md 日志规范与 cron 明细治理）：被 daily_job_runner
    调度的 ETL 脚本，其逐条明细日志会经由子进程 stdout 被 runner 捕获并写入
    logs/cron/{task}_{date}.log；若脚本自己再用 setup_logger 将明细写进 logs/{name}.log，
    就会造成明细重复落盘。本函数统一拆分：

    - 返回 (detail_logger, summary_logger)
    - detail_logger：仅保留 stdout（由 cron runner 捕获进 cron 明细文件），不写主文件
    - summary_logger：写 logs/{name}.log 汇总文件（轮转），不写 stdout，避免与明细 stdout 重复

    Args:
        name: logger 名（主汇总文件名 = logs/{name}.log）
        level: 日志级别

    Returns:
        tuple: (detail_logger, summary_logger)
    """
    detail = setup_logger(name, level=level)
    summary = setup_logger(f"{name}_summary", level=level, filename=f"{name}.log")
    # summary logger：移除默认 stdout（避免与明细 stdout 重复），仅保留写 {name}.log 的文件 handler
    for h in list(summary.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            summary.removeHandler(h)
            h.close()
    summary.propagate = False
    # detail logger：移除文件 handler，仅保留 stdout → cron runner 捕获
    for h in list(detail.handlers):
        if isinstance(h, logging.FileHandler):
            detail.removeHandler(h)
            h.close()
    detail.propagate = False
    return detail, summary


def setup_detail_stdout_only(name: str, level: int = logging.INFO) -> logging.Logger:
    """创建仅 stdout 的明细 logger（由 cron runner 捕获进 cron 明细文件），不写任何主日志文件。

    适用于日志治理：脚本明细只走 stdout（每日 cron 明细在 logs/cron/{task}_{date}.log），
    主日志文件只保留汇总（由调用方用 setup_logger 单独写）。等价于 setup_detail_and_summary_loggers
    返回的 detail 部分。
    """
    lg = setup_logger(name, level=level)
    for h in list(lg.handlers):
        if isinstance(h, logging.FileHandler):
            lg.removeHandler(h)
            h.close()
    lg.propagate = False
    return lg


def configure_root_logging(level: int = logging.INFO) -> logging.Logger:
    """统一配置 root logger 的 stdout handler（格式与全项目一致）。

    供使用 logging.basicConfig / logging.getLogger(__name__) 且无自建轮转 handler
    的后端服务与监控脚本调用，确保它们也遵循统一的日志格式规范。
    """
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return root
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(IsoFormatter(LOG_FORMAT))
    root.addHandler(handler)
    return root


def get_logger(name: str) -> logging.Logger:
    """
    获取已配置的日志记录器（便捷函数）

    Args:
        name: 日志记录器名称

    Returns:
        logger实例
    """
    return logging.getLogger(name)


def shutdown_logging():
    """安全关闭日志系统"""
    logging.shutdown()
