"""
test_diaries_cycle_check.py - 交易日记「周期闭环删改拦截」单元测试

覆盖 diaries._assert_cycle_not_done：未闭环放行 / 已闭环 400 / 周期不存在 404。
"""
import pytest
from fastapi import HTTPException

from core.api.router.pdca.diaries import _assert_cycle_not_done


class _FakeCursor:
    """模拟 psycopg2 游标，固定返回某个周期状态（支持 context manager）。"""

    def __init__(self, status: str | None):
        self._status = status

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.executed = (sql, params or ())

    def fetchone(self):
        return (self._status,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    """模拟 psycopg2 连接，携带 fake cursor。"""

    def __init__(self, status: str | None):
        self.cursor_result = status

    def cursor(self):
        return _FakeCursor(self.cursor_result)


def test_cycle_not_done_pass():
    """未闭环周期（如 DO）不抛异常。"""
    _assert_cycle_not_done(_FakeConn("DO"), 1)


def test_cycle_done_raises():
    """已闭环（DONE）周期抛 400 DIARY_CYCLE_CLOSED。"""
    with pytest.raises(HTTPException) as exc:
        _assert_cycle_not_done(_FakeConn("DONE"), 1)
    assert exc.value.status_code == 400
    assert "周期已闭环" in exc.value.detail


def test_cycle_missing_raises():
    """周期不存在抛 404 CYCLE_NOT_FOUND。"""
    with pytest.raises(HTTPException) as exc:
        _assert_cycle_not_done(_FakeConn(None), 999)
    assert exc.value.status_code == 404
    assert "周期不存在" in exc.value.detail