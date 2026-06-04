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
    level: int = logging.INFO
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
    os.chmod(log_dir, 0o755)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    log_file = os.path.join(log_dir, f"{name}.log")

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
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
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
