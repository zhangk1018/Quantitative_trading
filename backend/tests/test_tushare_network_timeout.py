"""Tushare 下载层硬超时（协作单 57.0）测试。

背景：2026-10-15 阶段 2（daily_import）静默死亡 —— Tushare 批量接口长时间无响应
（socket 空闲、CPU≈0），进程被杀、台账卡 running。修复为「守护线程 + join(timeout)」
硬超时：卡死线程置 daemon 不阻止进程退出，泄漏线程（仍 alive）超限即 fast-fail。

全部用例使用假 Tushare（不联网、不连库）。

2026-10-16 创建
"""
import sys
import time
from pathlib import Path

import pytest

# 保证 `collector.* / utils.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.datasource import tushare as ts_mod  # noqa: E402
from collector.datasource.tushare import (  # noqa: E402
    TushareDataSource,
    TushareTimeoutError,
    _call_with_hard_timeout,
)


@pytest.fixture(autouse=True)
def _reset_hung_threads():
    """隔离各用例：清空模块级泄漏线程列表。"""
    ts_mod._hung_threads.clear()
    yield
    ts_mod._hung_threads.clear()


class TestCallWithHardTimeout:
    """_call_with_hard_timeout 行为。"""

    def test_returns_within_deadline(self) -> None:
        """时限内完成正常返回。"""
        assert _call_with_hard_timeout(time.sleep, (0.05,), timeout=5) is None

    def test_raises_on_timeout(self) -> None:
        """超过时限抛 TushareTimeoutError（而非永久阻塞）。"""
        started = time.time()
        with pytest.raises(TushareTimeoutError):
            _call_with_hard_timeout(time.sleep, (30,), timeout=1, name='t.daily')
        assert time.time() - started < 3

    def test_passthrough_return_value(self) -> None:
        """func 的返回值原样透传。"""
        assert _call_with_hard_timeout(lambda: 42, timeout=5) == 42

    def test_exception_propagates(self) -> None:
        """func 抛出的异常原样透传（不吞成超时）。"""
        def _boom():
            raise ValueError('bad')
        with pytest.raises(ValueError):
            _call_with_hard_timeout(_boom, timeout=5)

    def test_zero_timeout_runs_synchronously(self) -> None:
        """timeout<=0 表示不设限，退化为同步执行。"""
        assert _call_with_hard_timeout(lambda: 7, timeout=0) == 7

    def test_hung_thread_limit_fast_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """在存卡死线程达上限后，后续调用直接 fast-fail（耗时 ≪ timeout）。"""
        monkeypatch.setattr(ts_mod, '_MAX_HUNG_THREADS', 1)
        with pytest.raises(TushareTimeoutError):
            _call_with_hard_timeout(time.sleep, (30,), timeout=1, name='t.a')
        started = time.time()
        with pytest.raises(TushareTimeoutError):
            _call_with_hard_timeout(time.sleep, (30,), timeout=5, name='t.b')
        assert time.time() - started < 0.5


class _HangingPro:
    """如半死连接般永久挂起的假 Tushare Pro。"""

    @staticmethod
    def daily(*args, **kwargs):
        time.sleep(30)


class TestTushareDataSourceDeadline:
    """数据源方法上的硬超时，且不被 RuntimeError 吞掉。"""

    @staticmethod
    def _connected_with(pro) -> TushareDataSource:
        src = TushareDataSource()
        src.connected = True
        src._pro = pro
        return src

    def test_batch_get_daily_timeout_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """batch_get_daily 硬超时 → TushareTimeoutError（非 RuntimeError）。"""
        monkeypatch.setattr(ts_mod, 'TUSHARE_BATCH_TIMEOUT', 1)
        src = self._connected_with(_HangingPro())
        started = time.time()
        with pytest.raises(TushareTimeoutError):
            src.batch_get_daily('2026-10-15')
        assert time.time() - started < 3

    def test_get_kline_timeout_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_kline 硬超时 → TushareTimeoutError（非 RuntimeError）。"""
        monkeypatch.setattr(ts_mod, 'TUSHARE_QUERY_TIMEOUT', 1)
        src = self._connected_with(_HangingPro())
        started = time.time()
        with pytest.raises(TushareTimeoutError):
            src.get_kline('000001')
        assert time.time() - started < 3
