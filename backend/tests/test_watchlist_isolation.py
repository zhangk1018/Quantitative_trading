"""
test_watchlist_isolation.py - 自选股按账号隔离测试（协作单 42.0 §7）

以直接调用 watchlist handler 的方式测试（本环境无 httpx，不依赖 FastAPI TestClient）：
- 未认证时访问自选股 → 401（get_current_user 拒绝）
- A/B 两账号自选股互不可见（增/删/查隔离）

运行（需要真实 DB）：
    cd backend && ../venv/bin/python -m pytest tests/test_watchlist_isolation.py -v
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from core.api.passwords import hash_password
from core.api.security import create_session_token
from core.api.dependencies import CurrentUser, get_current_user
from core.api.router.watchlist import WatchlistAddRequest, delete_watchlist, get_watchlist
from collector.db.database import get_db_session

_UID_PREFIX = "utest_wl"


def _create_user(username: str) -> None:
    with get_db_session() as db:
        db.execute(
            text("INSERT INTO users (username, password_hash, display_name, role) "
                 "VALUES (:u, :h, :u, 'user')"),
            {"u": username, "h": hash_password("password123")},
        )
        db.commit()


def _delete_user(username: str) -> None:
    with get_db_session() as db:
        db.execute(text("DELETE FROM user_watchlist WHERE user_id = :u"), {"u": username})
        db.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
        db.commit()


def _cu(username: str) -> CurrentUser:
    token = create_session_token(username, 1)
    return get_current_user(_fake_req(token))


def _fake_req(token: str):
    from types import SimpleNamespace
    return SimpleNamespace(cookies={"access_token": token})


@pytest.fixture()
def two_users():
    name_a = f"{_UID_PREFIX}_a"
    name_b = f"{_UID_PREFIX}_b"
    _create_user(name_a)
    _create_user(name_b)
    yield name_a, name_b
    _delete_user(name_a)
    _delete_user(name_b)


class TestWatchlistIsolation:
    def test_unauthenticated_401(self):
        from types import SimpleNamespace
        with pytest.raises(HTTPException) as e:
            get_current_user(SimpleNamespace(cookies={}))
        assert e.value.status_code == 401

    def test_a_cannot_see_b(self, two_users):
        name_a, name_b = two_users
        cu_a = _cu(name_a)
        from core.api.router.watchlist import add_watchlist
        add_watchlist(WatchlistAddRequest(code="600000"), current_user=cu_a)
        list_a = get_watchlist(current_user=_cu(name_a)).data
        list_b = get_watchlist(current_user=_cu(name_b)).data
        assert [i.code for i in list_a] == ["600000"]
        assert list_b == []

    def test_isolation_add_remove(self, two_users):
        name_a, name_b = two_users
        from core.api.router.watchlist import add_watchlist
        add_watchlist(WatchlistAddRequest(code="600000"), current_user=_cu(name_a))
        add_watchlist(WatchlistAddRequest(code="000001"), current_user=_cu(name_b))
        codes_a = {i.code for i in get_watchlist(current_user=_cu(name_a)).data}
        codes_b = {i.code for i in get_watchlist(current_user=_cu(name_b)).data}
        assert codes_a == {"600000"}
        assert codes_b == {"000001"}
        # A 删除自己的，不影响 B
        delete_watchlist("600000", current_user=_cu(name_a))
        assert get_watchlist(current_user=_cu(name_a)).data == []
        assert {i.code for i in get_watchlist(current_user=_cu(name_b)).data} == {"000001"}

    def test_b_delete_a_stock_not_found(self, two_users):
        name_a, name_b = two_users
        from core.api.router.watchlist import add_watchlist
        add_watchlist(WatchlistAddRequest(code="600000"), current_user=_cu(name_a))
        # B 删 A 的股票 → B 侧找不到 → 404，A 的不受影响
        resp = delete_watchlist("600000", current_user=_cu(name_b))
        assert resp.code == 404
        assert {i.code for i in get_watchlist(current_user=_cu(name_a)).data} == {"600000"}