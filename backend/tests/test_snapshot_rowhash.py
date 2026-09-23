"""
test_snapshot_rowhash.py - 快照缓存刷新检测纳入快照维度测试（协作单 41.0）

背景：此前 row_hash 仅基于 stock_quotes（OHLCV）行数。美股快照补录到
stock_daily_snapshot 而不改 OHLCV 时，row_hash 不变 → 刷新检测漏判 → 快照缓存
滞留旧数据（无美股），美股自编指标选股筛 0 只。本次修复纳入快照维度。

覆盖：
- _compute_row_hash 同时反映 OHLCV 与快照两个维度（任一变化即变）
- 仅 OHLCV 行数变化 → hash 变（仍能触发刷新）
- 仅快照行数变化（如美股补录）→ hash 变（协作单 41.0 核心）
- meta 写入与 _query_meta 计算的 hash 一致（三处计算点统一）

运行（无需真实数据库）：
    cd backend && ../venv/bin/python -m pytest tests/test_snapshot_rowhash.py -v
"""

from core.service.snapshot_service import SnapshotService


class TestComputeRowHash:
    """_compute_row_hash 同时纳入 OHLCV 与快照两个维度"""

    def test_same_input_same_hash(self):
        h1 = SnapshotService._compute_row_hash(100, 8000)
        h2 = SnapshotService._compute_row_hash(100, 8000)
        assert h1 == h2

    def test_ohlcv_change_changes_hash(self):
        """仅 OHLCV 行数变化 → hash 变化（原有行为保留）"""
        assert SnapshotService._compute_row_hash(100, 8000) != SnapshotService._compute_row_hash(120, 8000)

    def test_snapshot_change_changes_hash(self):
        """仅快照行数变化（如美股补录）→ hash 变化（协作单 41.0 核心）"""
        assert SnapshotService._compute_row_hash(100, 8000) != SnapshotService._compute_row_hash(100, 8205)

    def test_combined_change_changes_hash(self):
        """两维度同时变化 → hash 变化"""
        assert SnapshotService._compute_row_hash(100, 8000) != SnapshotService._compute_row_hash(120, 8205)


class FakeCursor:
    """顺序返回 _query_meta 的两条 COUNT 结果（stock_quotes / stock_daily_snapshot）"""

    def __init__(self, results):
        self._results = list(results)
        self._idx = 0

    def execute(self, *args):
        pass

    def fetchone(self):
        resp = self._results[self._idx]
        self._idx += 1
        return resp

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, results):
        self._results = results
        self.close_called = False

    def cursor(self):
        return FakeCursor(self._results)

    def close(self):
        self.close_called = True


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def getconn(self):
        return self._conn

    def putconn(self, conn):
        pass


class TestQueryMeta:
    """_query_meta 同时统计 OHLCV 与快照维度，纳入 row_hash"""

    def test_query_meta_includes_snapshot_dimension(self):
        pool = FakePool(FakeConn([("2026-09-22",), (12345,), (8205,)]))
        svc = SnapshotService.__new__(SnapshotService)
        svc._pool = pool
        latest, row_hash, count = svc._query_meta()
        assert latest == "2026-09-22"
        assert count == 12345
        # 快照维度 8205 参与 hash：计算相同输入应得相同 hash
        expected = SnapshotService._compute_row_hash(12345, 8205)
        assert row_hash == expected
        # 若快照维度变化，hash 应不同（验证纳入快照维度而非只算 OHLCV）
        diff = SnapshotService._compute_row_hash(12345, 8206)
        assert row_hash != diff