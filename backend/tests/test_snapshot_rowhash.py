"""
test_snapshot_rowhash.py - 快照缓存刷新检测纳入快照维度测试（协作单 41.0 / 43.0）

背景：此前 row_hash 仅基于 stock_quotes（OHLCV）行数。美股快照补录到
stock_daily_snapshot 而不改 OHLCV 时，row_hash 不变 → 刷新检测漏判 → 快照缓存
滞留旧数据（无美股），美股自编指标选股筛 0 只。本次修复纳入快照维度。

协作单 43.0 追加：快照改为按各市场"各自最新交易日"加载，哈希再纳入各市场
日期签名，避免「各市场日期整体前移、行数恰好不变 → 哈希不变 → 不刷新」。

覆盖：
- _compute_row_hash 同时反映 OHLCV / 快照行数 / 各市场日期签名（任一变化即变）
- 仅 OHLCV 行数变化 → hash 变（仍能触发刷新）
- 仅快照行数变化（如美股补录）→ hash 变（协作单 41.0 核心）
- 仅各市场日期变化（行数不变）→ hash 变（协作单 43.0 核心）
- meta 写入与 _query_meta 计算的 hash 一致（三处计算点统一）

运行（无需真实数据库）：
    cd backend && ../venv/bin/python -m pytest tests/test_snapshot_rowhash.py -v
"""

from core.service.snapshot_service import SnapshotService


class TestComputeRowHash:
    """_compute_row_hash 同时纳入 OHLCV、快照行数与各市场日期三个维度"""

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

    def test_market_date_change_changes_hash(self):
        """仅各市场日期前移（行数完全相同）→ hash 变化（协作单 43.0 核心）

        若不纳入日期签名，会出现「cn/hk 由 9/25 前进到 9/28 且当日代码数恰好
        相同 → 哈希不变 → 快照缓存不刷新」的漏判。
        """
        before = {'cn': '2026-09-25', 'hk': '2026-09-25', 'us': '2026-09-25'}
        after = {'cn': '2026-09-28', 'hk': '2026-09-28', 'us': '2026-09-25'}
        assert (SnapshotService._compute_row_hash(100, 7599, before)
                != SnapshotService._compute_row_hash(100, 7599, after))

    def test_market_signature_is_order_insensitive(self):
        """哈希签名按 market 排序拼接，与 dict 插入顺序无关"""
        a = {'us': '2026-09-25', 'cn': '2026-09-28'}
        b = {'cn': '2026-09-28', 'us': '2026-09-25'}
        assert SnapshotService._compute_row_hash(100, 7599, a) == SnapshotService._compute_row_hash(100, 7599, b)


class FakeCursor:
    """按 _query_meta 的查询顺序返回：①各市场最新日 CTE → fetchall ②OHLCV 计数 → fetchone"""

    def __init__(self, market_rows, ohlcv_count):
        self._market_rows = market_rows
        self._ohlcv_count = ohlcv_count

    def execute(self, *args):
        pass

    def fetchall(self):
        return self._market_rows

    def fetchone(self):
        return (self._ohlcv_count,)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, market_rows, ohlcv_count):
        self._market_rows = market_rows
        self._ohlcv_count = ohlcv_count
        self.close_called = False

    def cursor(self):
        return FakeCursor(self._market_rows, self._ohlcv_count)

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
    """_query_meta 按市场维度统计快照，纳入 row_hash"""

    def test_query_meta_includes_snapshot_dimension(self):
        pool = FakePool(FakeConn(
            [('cn', '2026-09-28', 5210), ('hk', '2026-09-28', 2184), ('us', '2026-09-28', 8205)],
            12345,
        ))
        svc = SnapshotService.__new__(SnapshotService)
        svc._pool = pool
        latest, row_hash, count, market_latest = svc._query_meta()
        assert latest == '2026-09-28'
        assert count == 12345
        assert market_latest == {'cn': '2026-09-28', 'hk': '2026-09-28', 'us': '2026-09-28'}
        # 快照维度 = 各市场最新日行数之和
        expected = SnapshotService._compute_row_hash(12345, 5210 + 2184 + 8205, market_latest)
        assert row_hash == expected
        # 若快照维度变化，hash 应不同（验证纳入快照维度而非只算 OHLCV）
        assert row_hash != SnapshotService._compute_row_hash(12345, 5210 + 2184 + 8206, market_latest)

    def test_query_meta_latest_is_max_of_markets(self):
        """latest = 各市场最新日的最大值（滞后市场不拉低上界）"""
        pool = FakePool(FakeConn(
            [('cn', '2026-09-28', 5210), ('hk', '2026-09-28', 2184), ('us', '2026-09-25', 205)],
            12345,
        ))
        svc = SnapshotService.__new__(SnapshotService)
        svc._pool = pool
        latest, _, _, market_latest = svc._query_meta()
        assert latest == '2026-09-28'
        assert market_latest['us'] == '2026-09-25'
        assert SnapshotService._compute_row_hash(
            12345, 5210 + 2184 + 205, market_latest) != SnapshotService._compute_row_hash(
            12345, 5210 + 2184 + 205, {'cn': '2026-09-28', 'hk': '2026-09-28', 'us': '2026-09-28'})