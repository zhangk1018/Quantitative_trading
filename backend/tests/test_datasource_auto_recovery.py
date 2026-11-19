"""数据源自动恢复测试（2026-11-19）。

背景：Baostock 一次 get_kline 网络错误触发 failover 到 Tushare 后不会切回。
原因是 health_check 默认实现对「已断开」的源直接返回 False（见 BaseDataSource），
auto_recovery 永远拿不到 HEALTHY 判定。修复：健康检查时对断开的主源先重连再判定。

全部用例使用假数据源（不联网、不连库）。
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.datasource.base import (  # noqa: E402
    DataSourceManager, DataSourceStatus, SwitchStrategy,
)


class FakeSource:
    """最小假数据源：记录 connect 调用次数，health_check 固定返回健康。"""

    def __init__(self, name: str, connected: bool = False):
        self._name = name
        self.connected = connected
        self.connect_calls = 0
        self.disconnect_calls = 0

    @property
    def name(self) -> str:
        return self._name

    def connect(self) -> bool:
        self.connect_calls += 1
        self.connected = True
        return True

    def disconnect(self) -> bool:
        self.disconnect_calls += 1
        self.connected = False
        return True

    def health_check(self) -> bool:
        return True


def _manager(primary: FakeSource, backup: FakeSource, auto_recovery: bool = True) -> DataSourceManager:
    mgr = DataSourceManager(
        sources=[
            {'source': primary, 'weight': 1, 'priority': 0},
            {'source': backup, 'weight': 1, 'priority': 1},
        ],
        strategy=SwitchStrategy.FAILOVER,
        health_check_interval=0,
        auto_recovery=auto_recovery,
    )
    mgr.current_source = backup
    mgr.current_source_index = 1
    mgr.last_health_check = 0
    return mgr


class TestAutoRecovery:
    def test_disconnected_primary_reconnects_and_switches_back(self) -> None:
        """failover 后主源处于断开态 → 健康检查重连并切回（只登录一次）。"""
        primary = FakeSource('baostock', connected=False)
        backup = FakeSource('tushare', connected=True)
        mgr = _manager(primary, backup)

        mgr._perform_health_check()

        assert primary.connect_calls == 1
        assert mgr.current_source is primary
        assert mgr.health_status['baostock'] == DataSourceStatus.HEALTHY
        assert backup.connected is False

    def test_connected_primary_not_reconnected(self) -> None:
        """主源已连接时不应重复登录。"""
        primary = FakeSource('baostock', connected=True)
        backup = FakeSource('tushare', connected=True)
        mgr = _manager(primary, backup)

        mgr._perform_health_check()

        assert primary.connect_calls == 0
        assert mgr.current_source is primary

    def test_auto_recovery_disabled_keeps_backup(self) -> None:
        primary = FakeSource('baostock', connected=False)
        backup = FakeSource('tushare', connected=True)
        mgr = _manager(primary, backup, auto_recovery=False)

        mgr._perform_health_check()

        assert primary.connect_calls == 0
        assert mgr.current_source is backup
        assert mgr.health_status['baostock'] == DataSourceStatus.UNHEALTHY
