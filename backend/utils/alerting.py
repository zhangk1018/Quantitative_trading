"""
告警落盘工具（协作单 30.0 V6 / P0 数据质量监控）

供 ① 指数探针 check_index_integrity / ② 监控 market 维度 data_quality_monitor /
③ 复权跳变监控 共用：把形如 {'level', 'message', 'market'} 的告警统一追加到
`backend/logs/monitoring/alerts.log`，供看板（monitor.html 汇总展示）与人工晨检读取。

告警落点口径（K 2026-09-03 确认）：仅落 `logs/monitoring/alerts.log` + 看板汇总，
**不做群推送**；由 K 每日晨会前检查看板。
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from utils.logger import setup_logger

logger = setup_logger('alerting')

# alerts.log 统一路径（可被环境变量 ALERTS_LOG 覆盖）
_ROOT_DIR = Path(__file__).resolve().parents[1]  # backend/
DEFAULT_ALERT_LOG = _ROOT_DIR / 'logs' / 'monitoring' / 'alerts.log'


def get_alert_log_path() -> Path:
    """返回告警日志路径（优先环境变量 ALERTS_LOG，否则默认 backend/logs/monitoring/alerts.log）。"""
    override = os.environ.get('ALERTS_LOG')
    return Path(override) if override else DEFAULT_ALERT_LOG


def append_alerts(alerts: List[Dict[str, str]]) -> int:
    """把告警字典列表追加到 alerts.log（幂等，逐条各追加一行）。

    Args:
        alerts: 形如 [{'level': 'WARNING'|'CRITICAL', 'market': str, 'message': str}, ...]

    Returns:
        实际写入的告警条数
    """
    path = get_alert_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    for a in alerts:
        level = (a.get('level') or 'WARNING').upper()
        market = a.get('market')
        message = a.get('message', '').strip()
        if not message:
            continue
        try:
            with path.open('a', encoding='utf-8') as f:
                prefix = f"[{datetime.now().isoformat(timespec='seconds')}] [{level}]"
                if market:
                    prefix += f" [{market}]"
                f.write(f"{prefix} {message}\n")
            written += 1
        except OSError as e:
            logger.error(f"❌ 写入告警日志失败({path}): {e}")
    if written:
        logger.warning(f"🔔 已写入 {written} 条告警: {path}")
    return written


def tail_alerts(max_lines: Optional[int] = 200) -> List[str]:
    """读取 alerts.log 末尾若干行（供看板/接口汇总展示）。

    Args:
        max_lines: 最多返回的行数

    Returns:
        非空行列表（从旧到新）
    """
    path = get_alert_log_path()
    if not path.exists():
        return []
    try:
        return [ln.rstrip('\n') for ln in path.read_text(encoding='utf-8').splitlines() if ln.strip()]
    except OSError as e:
        logger.error(f"❌ 读取告警日志失败({path}): {e}")
        return []