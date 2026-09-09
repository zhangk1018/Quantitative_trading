"""日志保留清理 —— 按保留天数删除 logs/cron 下每日任务明细日志。

cron 任务明细命名规范：`logs/cron/{task_name}_{YYYYMMDD}.log`（由 daily_job_runner
的 setup_task_logger 生成，每日一个，无轮转上限）。本工具按文件命名中的日期删除
超过保留天数（默认 30 天）的历史明细，控制磁盘占用。

用法：
    from utils.log_retention import cleanup_cron_logs
    removed = cleanup_cron_logs('/path/to/logs/cron', keep_days=30)
"""
import os
import re
from datetime import datetime, timedelta
from typing import Optional

# 匹配 {task}_{YYYYMMDD}.log，仅针对带日期的每日明细，避开 launchd stdout/stderr 单文件
_DAILY_CRON_RE = re.compile(r'^.+_(?P<ymd>\d{8})\.log$')


def cleanup_cron_logs(cron_dir: Optional[str], keep_days: int = 30) -> int:
    """删除 logs/cron 下超过 keep_days 天的每日任务明细日志。

    Args:
        cron_dir: cron 日志目录（如 `logs/cron`）。为空或不存在时直接返回 0。
        keep_days: 保留天数，>0 的整数，默认 30。文件名日期早于（今天 - keep_days）的文件被删除。

    Returns:
        实际删除的文件数。
    """
    if not cron_dir or not os.path.isdir(cron_dir):
        return 0

    deadline = datetime.now().date() - timedelta(days=max(1, keep_days))
    removed = 0
    for name in os.listdir(cron_dir):
        match = _DAILY_CRON_RE.match(name)
        if not match:
            continue
        try:
            file_date = datetime.strptime(match.group('ymd'), '%Y%m%d').date()
        except ValueError:
            continue
        if file_date < deadline:
            path = os.path.join(cron_dir, name)
            try:
                os.remove(path)
                removed += 1
            except OSError:
                continue
    return removed