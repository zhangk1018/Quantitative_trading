"""协作单 56.0：阶段门禁 + 行数骤降告警 单测（假 engine，不连库/不联网）。

背景（2026-10-15）：A 股阶段 2（daily_import）**静默死亡**（当日日线 0 落库、台账卡 running），
阶段 3 仍照跑并全部报成功 → 对近乎空的数据算指标/宽表，形成「假成功静默丢一天数据」
（当日 cn 仅 26 行 vs 近 20 日中位数 ~5211）。

覆盖：
- `check_coverage_gate`：阶段 3 前置门禁（当日覆盖 / 近 20 日中位数 < 90% → 拒绝执行）
- `check_task_rows_collapse`：任务行数骤降告警（本次 / 近 N 次中位数 < 50% → 告警）
"""
import importlib.util
import os
import sys

import pytest

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_module():
    """按相对路径加载 daily_job_runner 模块（与 test_daily_job_runner.py 同风格）。"""
    module_path = os.path.join(str(BACKEND_DIR), "cron", "daily_job_runner.py")
    spec = importlib.util.spec_from_file_location("daily_job_runner_gate", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dj():
    return _load_module()


# ===================== 假 engine =====================
class _FakeResult:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, parent):
        self.parent = parent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        q = str(sql)
        if 'rows_affected' in q:                     # 行数骤降查询
            return _FakeResult(rows=[(r,) for r in self.parent.task_rows])
        if 'percentile_cont' in q:                   # 中位数基线
            return _FakeResult(scalar=self.parent.median)
        return _FakeResult(scalar=self.parent.today_count)   # 当日覆盖数


class _FakeEngine:
    def __init__(self, today_count=0, median=0.0, task_rows=None):
        self.today_count = today_count
        self.median = median
        self.task_rows = task_rows or []

    def connect(self):
        return _FakeConn(self)


class TestCoverageGate:
    """阶段 3 前置门禁。"""

    def test_pass_when_ratio_ok(self, dj):
        eng = _FakeEngine(today_count=5214, median=5211.0)
        ok, msg = dj.check_coverage_gate(eng, '2026-10-14')
        assert ok is True
        assert '5214' in msg and '100.1%' in msg

    def test_block_when_rows_collapsed(self, dj):
        """复刻 10-15 事故：当日 26 只 vs 中位数 5211（0.5%）→ 拒绝执行。"""
        eng = _FakeEngine(today_count=26, median=5211.0)
        ok, msg = dj.check_coverage_gate(eng, '2026-10-15')
        assert ok is False
        assert '26 只' in msg and '0.5%' in msg

    def test_env_switch_disables_gate(self, dj, monkeypatch):
        monkeypatch.setenv('CN_STAGE3_GATE', '0')
        eng = _FakeEngine(today_count=0, median=5211.0)
        ok, msg = dj.check_coverage_gate(eng, '2026-10-15')
        assert ok is True and 'CN_STAGE3_GATE=0' in msg

    def test_pass_when_no_baseline(self, dj):
        """新库无近 20 日基线 → 跳过门禁（不误阻断）。"""
        eng = _FakeEngine(today_count=26, median=0.0)
        ok, msg = dj.check_coverage_gate(eng, '2026-10-15')
        assert ok is True and '跳过门禁' in msg


class TestRowsCollapse:
    """任务行数骤降告警（仅告警，不阻断）。"""

    def test_alerts_on_drastic_drop(self, dj):
        """复刻事故：本次 26 行 vs 历史 5209~5214 → 返回告警文案。"""
        eng = _FakeEngine(task_rows=[26, 5209, 5210, 5212, 5214])
        msg = dj.check_task_rows_collapse(eng, 'daily_import', 2)
        assert msg and '行数骤降' in msg and '0.5%' in msg

    def test_none_when_normal(self, dj):
        eng = _FakeEngine(task_rows=[5214, 5209, 5210, 5212])
        assert dj.check_task_rows_collapse(eng, 'daily_import', 2) is None

    def test_none_when_sample_too_small(self, dj):
        """样本 < 3 次不判（避免新任务误报）。"""
        eng = _FakeEngine(task_rows=[26, 5210])
        assert dj.check_task_rows_collapse(eng, 'daily_import', 2) is None

    def test_whitelist_excludes_volatile_tasks(self, dj):
        """天然波动大的任务（signal_precompute 等）不入白名单，避免告警噪声。"""
        assert 'daily_import' in dj.ROWS_COLLAPSE_TASKS
        assert 'daily_sync' in dj.ROWS_COLLAPSE_TASKS
        assert 'signal_precompute' not in dj.ROWS_COLLAPSE_TASKS
        assert 'pattern_precompute' not in dj.ROWS_COLLAPSE_TASKS
