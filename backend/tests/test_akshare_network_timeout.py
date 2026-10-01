"""AkShare 网络调用硬超时（network_deadline）测试。

背景：AkShare 各接口不暴露 timeout 参数（requests 默认无限等待）。2026-10-01 美股
日线清洗因系统休眠导致 TCP 连接半死，进程永久阻塞在 SSL_read，僵死 3.5 小时、
205 只标的只落 61 只。修复引入 `network_deadline`，以 SIGALRM 给每次网络调用设硬超时，
超时抛 NetworkTimeoutError，由调用方原有 try/except 兜底（跳过该标的或降级下一数据源）。

全部用例使用假 AkShare，不访问网络与数据库。

2026-10-01 创建
"""
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

# 保证 `collector.* / utils.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.datasource import akshare as ak_mod  # noqa: E402
from collector.datasource.akshare import (  # noqa: E402
    AkShareDataSource,
    NetworkTimeoutError,
    network_deadline,
)


class TestNetworkDeadline:
    """network_deadline 上下文管理器行为。"""

    def test_returns_normally_within_deadline(self) -> None:
        """时限内完成时不抛异常。"""
        with network_deadline(5):
            time.sleep(0.05)

    def test_raises_network_timeout_error_on_timeout(self) -> None:
        """超过时限抛 NetworkTimeoutError（而非永久阻塞）。"""
        started = time.time()
        with pytest.raises(NetworkTimeoutError):
            with network_deadline(1):
                time.sleep(5)
        assert time.time() - started < 3

    def test_timer_cleared_after_exit(self) -> None:
        """退出后 SIGALRM 定时器被清除，不会误伤后续代码。"""
        with network_deadline(1):
            pass
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)

    def test_disabled_when_seconds_non_positive(self) -> None:
        """seconds<=0 表示不设限。"""
        with network_deadline(0):
            time.sleep(0.05)

    def test_disabled_in_non_main_thread(self) -> None:
        """非主线程退化为不设限（SIGALRM 在线程中不可用）。"""
        outcome = {}

        def worker() -> None:
            try:
                with network_deadline(1):
                    time.sleep(1.2)
                outcome['result'] = 'done'
            except Exception as exc:  # noqa: BLE001 - 断言超时异常类型需捕获任意异常
                outcome['result'] = type(exc).__name__

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=10)
        assert outcome.get('result') == 'done'


class TestDownloadSingleTimeout:
    """下载超时时跳过该标的，不拖死进程。"""

    @staticmethod
    def _hanging_ak() -> type:
        """构造一个「如半死连接般永久挂起」的假 AkShare。"""

        class _HangingAk:
            @staticmethod
            def stock_us_daily(*args, **kwargs):
                time.sleep(30)

            @staticmethod
            def stock_hk_daily(*args, **kwargs):
                time.sleep(30)

        return _HangingAk

    def test_us_download_returns_none_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """美股标的下载超时 → download_single 返回 None（不抛异常、不阻塞）。"""
        monkeypatch.setattr(ak_mod, 'ak', self._hanging_ak())
        monkeypatch.setattr(ak_mod, '_NETWORK_TIMEOUT_SECONDS', 1)

        source = AkShareDataSource(market='us')
        started = time.time()
        assert source.download_single('AAPL') is None
        assert time.time() - started < 3

    def test_hk_download_returns_none_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """港股标的下载超时 → download_single 返回 None。"""
        monkeypatch.setattr(ak_mod, 'ak', self._hanging_ak())
        monkeypatch.setattr(ak_mod, '_NETWORK_TIMEOUT_SECONDS', 1)

        source = AkShareDataSource(market='hk')
        started = time.time()
        assert source.download_single('0700.HK') is None
        assert time.time() - started < 3