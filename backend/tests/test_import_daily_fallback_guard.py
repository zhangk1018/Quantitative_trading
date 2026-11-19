"""增量导入 fallback 守卫测试（2026-11-19 协作单：Tushare 502 空返回触发全市场逐只超时）。

背景：2026-11-18 阶段2 daily_import 超时 60 分钟。根因是 Tushare 网关 502 时官方库
`if res:` 判假 → 静默返回空 DataFrame，被误判为「当日无数据」，进而触发全市场
5249 只逐只 fallback；按数据源限速（Baostock 20 次/分、Tushare 45 次/分）需 2~4 小时。

修复：
  1. TushareDataSource.service_alive() 用已知历史交易日探针区分「网关 5xx」与「无数据」；
  2. 空返回且服务不可用 → 抛 TushareServiceError（可重试），不再静默当无数据；
  3. 仅「批量成功但当日不完整」才进入逐只 fallback，并设时间上限。

全部用例使用假数据源 / 假 HTTP（不联网、不连库）。
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.datasource import tushare as ts_mod  # noqa: E402
from collector.datasource.tushare import TushareDataSource, TushareServiceError  # noqa: E402
from collector.etl.import_daily_data import DailyDataImporter  # noqa: E402


class TestDecideFallback:
    """_decide_fallback：只有「批量成功但不完整」才允许逐只 fallback。"""

    @staticmethod
    def _d(attempted, batch_success, batch_failed, completeness_ok):
        return DailyDataImporter._decide_fallback(
            attempted, batch_success, batch_failed, completeness_ok)

    def test_no_trade_day(self) -> None:
        assert self._d(False, False, False, True) == (False, 'no_trade_day')

    def test_hard_failed_skips_fallback(self) -> None:
        """数据源 502/超时（硬失败）→ 不进入逐只 fallback。"""
        assert self._d(True, False, True, True) == (False, 'batch_hard_failed')

    def test_empty_day_skips_fallback(self) -> None:
        """接口正常但当日无数据（未发布）→ 不进入逐只 fallback。"""
        assert self._d(True, False, False, True) == (False, 'batch_empty')

    def test_incomplete_triggers_fallback(self) -> None:
        """批量成功但完整度不足 → 进入（有上限的）逐只补全。"""
        assert self._d(True, True, False, False) == (True, 'incomplete')

    def test_complete_no_fallback(self) -> None:
        assert self._d(True, True, False, True) == (False, 'complete')


class _NullCursor:
    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _NullConn:
    def cursor(self):
        return _NullCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _NullStorage:
    def transaction(self):
        return _NullConn()


class TestSingleThreadBudget:
    """_single_thread_incremental 的时间上限：避免整条任务被 60 分钟超时杀死。"""

    @staticmethod
    def _make_importer(processed):
        imp = DailyDataImporter.__new__(DailyDataImporter)
        imp.storage = _NullStorage()
        imp._get_last_date_in_range = lambda codes, s, e: {}
        imp._is_valid_delisted = lambda d: False
        imp.update_task_progress = lambda *a, **k: None

        def _import(code, start, end):
            processed.append(code)
            time.sleep(0.02)
            return 1

        imp.import_stock_data = _import
        return imp

    def test_budget_stops_loop(self) -> None:
        processed = []
        imp = self._make_importer(processed)
        codes = [f'6{i:05d}' for i in range(100)]
        sc, fc, tr = imp._single_thread_incremental(
            codes, '2026-11-18', min_start_date='2026-10-19', max_seconds=0.05)
        assert 0 < len(processed) < len(codes)
        assert sc == len(processed)
        assert tr == len(processed)

    def test_no_budget_processes_all(self) -> None:
        processed = []
        imp = self._make_importer(processed)
        codes = [f'6{i:05d}' for i in range(5)]
        sc, _, tr = imp._single_thread_incremental(codes, '2026-11-18', max_seconds=None)
        assert len(processed) == 5
        assert sc == 5 and tr == 5


class TestServiceAlive:
    """service_alive：用历史交易日探针识别网关 5xx。"""

    @staticmethod
    def _connected_src() -> TushareDataSource:
        src = TushareDataSource()
        src.connected = True
        src._pro = SimpleNamespace()
        src._get_token = lambda: 'fake-token'
        src._wait_for_rate_limit = lambda: None
        return src

    def test_not_connected_assumes_alive(self) -> None:
        """未连接场景保持原有语义（不做网络探测）。"""
        src = TushareDataSource()
        assert src.service_alive() is True

    def test_http_502_is_dead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = self._connected_src()
        monkeypatch.setattr(ts_mod.requests, 'post',
                            lambda *a, **k: SimpleNamespace(status_code=502, json=lambda: {}))
        assert src.service_alive() is False

    def test_empty_items_is_dead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = self._connected_src()
        payload = {'code': 0, 'data': {'fields': [], 'items': []}}
        monkeypatch.setattr(ts_mod.requests, 'post',
                            lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: payload))
        assert src.service_alive() is False

    def test_probe_with_rows_is_alive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = self._connected_src()
        payload = {'code': 0, 'data': {'fields': ['ts_code'], 'items': [['000001.SZ']]}}
        monkeypatch.setattr(ts_mod.requests, 'post',
                            lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: payload))
        assert src.service_alive() is True


class TestBatchEmptySemantics:
    """batch_get_daily：空返回需区分「服务不可用」与「当日无数据」。"""

    @staticmethod
    def _src() -> TushareDataSource:
        src = TushareDataSource()
        src.connected = True
        src._pro = SimpleNamespace(daily=lambda **kwargs: pd.DataFrame())
        src._wait_for_rate_limit = lambda: None
        return src

    def test_empty_and_dead_raises_service_error(self) -> None:
        src = self._src()
        src.service_alive = lambda: False
        with pytest.raises(TushareServiceError):
            src.batch_get_daily('2026-11-18')

    def test_empty_but_alive_returns_empty(self) -> None:
        src = self._src()
        src.service_alive = lambda: True
        df = src.batch_get_daily('2026-11-18')
        assert df is not None and df.empty
