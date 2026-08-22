"""
test_records_auto_match.py - 交易记录自动匹配交易计划单元测试
"""
from core.api.router.pdca.records import auto_match_plan_id


class _FakeCursor:
    """模拟 psycopg2 游标的 execute/fetchone，便于无 DB 单测"""

    def __init__(self, result):
        self.result = result
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.executed.append((sql, params or ()))

    def fetchone(self):
        return self.result


def test_auto_match_returns_latest_plan():
    cur = _FakeCursor((7,))
    assert auto_match_plan_id(cur, 5, "600211") == 7
    sql, params = cur.executed[0]
    assert "pdca.trading_plan" in sql
    assert "pdca_cycle_id" in sql
    assert "deleted_at IS NULL" in sql
    assert "ORDER BY id DESC LIMIT 1" in sql
    assert params == (5, "600211")


def test_auto_match_no_plan_returns_none():
    cur = _FakeCursor(None)
    assert auto_match_plan_id(cur, 5, "000001") is None