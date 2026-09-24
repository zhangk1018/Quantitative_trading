"""
test_auth.py - 多用户账号体系认证核心测试（协作单 42.0 §7）

以直接调用路由 handler 的方式测试（本环境无 httpx，不依赖 FastAPI TestClient）：
- pbkdf2 散列/校验/盐隔离/密码策略
- token 携带 sub/ver
- 登录成功/失败/禁用（login handler）
- 登录不踢旧会话（版本号不变）
- 改密/禁用后旧 token 失效（token_version+1）
- 注册关闭 403 / 注册限流 429 / 重复 409
- get_current_user DB 故障返回 503；未认证 401；禁用账号 401
- require_admin 权限 / 管理员禁用用户

运行（需要真实 DB，users 表由 V014 迁移创建）：
    cd backend && ../venv/bin/python -m pytest tests/test_auth.py -v
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core.api.config import settings
from core.api.passwords import hash_password, password_meets_policy, verify_password
from core.api.security import create_session_token, decode_session_token
from core.api.dependencies import CurrentUser, get_current_user, require_admin
from core.api.router.auth import (
    ChangePasswordRequest,
    LoginRequest,
    UserUpdateRequest,
    change_password,
    login,
    logout,
    logout_all,
    register,
    update_user,
)
from collector.db.database import get_db_session

_UID_PREFIX = "utest_auth"


def _create_user(username: str, password: str = "password123", role: str = "user") -> None:
    with get_db_session() as db:
        db.execute(
            text("INSERT INTO users (username, password_hash, display_name, role, is_active) "
                 "VALUES (:u, :h, :u, :role, TRUE)"),
            {"u": username, "h": hash_password(password), "role": role},
        )
        db.commit()


def _delete_user(username: str) -> None:
    with get_db_session() as db:
        db.execute(text("DELETE FROM user_watchlist WHERE user_id = :u"), {"u": username})
        db.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
        db.commit()


def _token_version(username: str) -> int:
    with get_db_session() as db:
        return int(db.execute(text("SELECT token_version FROM users WHERE username=:u"),
                              {"u": username}).scalar_one())


def _user_id(username: str) -> int:
    with get_db_session() as db:
        return int(db.execute(text("SELECT id FROM users WHERE username=:u"),
                              {"u": username}).scalar_one())


def _fake_req(token: str, client_host: str = "127.0.0.1"):
    """构造 get_current_user / register 所需的轻量请求对象。"""
    return SimpleNamespace(cookies={"access_token": token},
                           client=SimpleNamespace(host=client_host))


# ============================================
# 纯函数：散列 / 策略
# ============================================
class TestPasswords:
    def test_hash_verify_roundtrip(self):
        h = hash_password("S3cret_Pass")
        assert h.count("$") == 2
        assert verify_password("S3cret_Pass", h) is True

    def test_wrong_password_rejected(self):
        h = hash_password("correct-pw")
        assert verify_password("wrong", h) is False

    def test_salt_isolation(self):
        h1 = hash_password("same-pw-1")
        h2 = hash_password("same-pw-1")
        assert h1 != h2
        assert verify_password("same-pw-1", h1) and verify_password("same-pw-1", h2)

    def test_malformed_stored_rejected(self):
        assert verify_password("any", "not-a-valid-hash") is False

    def test_policy(self):
        assert password_meets_policy("short") is False
        assert password_meets_policy("") is False
        assert password_meets_policy("12345678") is True


# ============================================
# 纯函数：token 携带 sub/ver
# ============================================
class TestToken:
    def test_token_carries_sub_ver(self):
        token = create_session_token("alice", 3)
        payload = decode_session_token(token)
        assert payload["sub"] == "alice"
        assert payload["ver"] == 3


# ============================================
# 登录 handler
# ============================================
class TestLogin:
    def test_login_success(self):
        uname = f"{_UID_PREFIX}_ok"
        _create_user(uname, "password123", "user")
        try:
            resp = login(LoginRequest(username=uname, password="password123"), response=Response())
            assert resp.data["username"] == uname
            assert resp.data["role"] == "user"
            # 登录不改变 token_version
            assert _token_version(uname) == 1
        finally:
            _delete_user(uname)

    def test_login_two_devices_do_not_kick(self):
        uname = f"{_UID_PREFIX}_two"
        _create_user(uname, "password123")
        try:
            login(LoginRequest(username=uname, password="password123"), response=Response())
            login(LoginRequest(username=uname, password="password123"), response=Response())
            # key：多次登录不递增 token_version，多设备并存
            assert _token_version(uname) == 1
        finally:
            _delete_user(uname)

    def test_login_bad_credentials(self):
        uname = f"{_UID_PREFIX}_bad"
        _create_user(uname, "password123")
        try:
            with pytest.raises(HTTPException) as e:
                login(LoginRequest(username=uname, password="wrong"), response=Response())
            assert e.value.status_code == 401
            assert e.value.detail["code"] == "bad_credentials"
        finally:
            _delete_user(uname)

    def test_login_nonexistent_user(self):
        with pytest.raises(HTTPException) as e:
            login(LoginRequest(username="no_such_user_xyz", password="whatever"), response=Response())
        assert e.value.status_code == 401
        assert e.value.detail["code"] == "bad_credentials"

    def test_login_disabled(self):
        uname = f"{_UID_PREFIX}_dis"
        with get_db_session() as db:
            db.execute(text("INSERT INTO users (username, password_hash, role, is_active) "
                            "VALUES (:u, :h, 'user', FALSE)"),
                       {"u": uname, "h": hash_password("password123")})
            db.commit()
        try:
            with pytest.raises(HTTPException) as e:
                login(LoginRequest(username=uname, password="password123"), response=Response())
            assert e.value.status_code == 403
            assert e.value.detail["code"] == "disabled"
        finally:
            _delete_user(uname)


# ============================================
# 会话语义：改密/禁用踢旧会话
# ============================================
class TestSessionSemantics:
    def _cu(self, token: str) -> CurrentUser:
        return get_current_user(_fake_req(token))

    def test_change_password_kicks_old_token(self):
        uname = f"{_UID_PREFIX}_chg"
        _create_user(uname, "password123")
        try:
            old_token = create_session_token(uname, 1)  # DB token_version=1
            cu = self._cu(old_token)
            assert cu.username == uname
            # 改密（旧密码正确）→ 204，token_version+1
            change_password(
                ChangePasswordRequest(old_password="password123", new_password="newpass12345"),
                current_user=cu,
            )
            assert _token_version(uname) == 2
            # 旧 token(ver=1) 失效
            with pytest.raises(HTTPException) as e:
                self._cu(old_token)
            assert e.value.status_code == 401
            # 新 token(ver=2) 正常
            assert self._cu(create_session_token(uname, 2)).username == uname
        finally:
            _delete_user(uname)

    def test_disable_invalidates_old_token(self):
        uname = f"{_UID_PREFIX}_dis2"
        _create_user(uname, "password123")
        try:
            token = create_session_token(uname, 1)
            assert self._cu(token).username == uname
            # 模拟禁用：is_active=False + token_version+1
            with get_db_session() as db:
                db.execute(text("UPDATE users SET is_active = FALSE, token_version = token_version + 1 "
                                "WHERE username = :u"), {"u": uname})
                db.commit()
            with pytest.raises(HTTPException) as e:
                self._cu(token)
            assert e.value.status_code == 401
            assert e.value.detail["code"] == "disabled"
        finally:
            _delete_user(uname)

    def test_unauthenticated_no_token(self):
        with pytest.raises(HTTPException) as e:
            get_current_user(_fake_req(None))
        assert e.value.status_code == 401
        assert e.value.detail["code"] == "unauthenticated"

    def test_missing_sub_rejected(self):
        # 旧版无 sub 的 token（仅 exp）应被判未认证
        from jose import jwt as _jwt
        from datetime import datetime, timedelta, timezone
        from core.api.config import settings as _s
        stale = _jwt.encode({"exp": datetime.now(timezone.utc) + timedelta(seconds=60)},
                            _s.session_secret, algorithm="HS256")
        with pytest.raises(HTTPException) as e:
            get_current_user(_fake_req(stale))
        assert e.value.status_code == 401


# ============================================
# 注册
# ============================================
class TestRegister:
    def test_register_closed_by_default(self):
        from types import SimpleNamespace as _ns
        req = _ns(client=_ns(host="127.0.0.1"))
        with pytest.raises(HTTPException) as e:
            register(_register_req(f"{_UID_PREFIX}_r"), req)
        assert e.value.status_code == 403
        assert e.value.detail["code"] == "register_closed"


def _register_req(username: str, password: str = "password123", display_name: str = None):
    from core.api.router.auth import RegisterRequest
    return RegisterRequest(username=username, password=password, display_name=display_name)


class TestRegisterRateLimit:
    def test_register_rate_limited(self, monkeypatch):
        from types import SimpleNamespace as _ns
        monkeypatch.setattr(settings, "auth_allow_register", True)
        monkeypatch.setattr(settings, "register_rate_limit", 2)
        monkeypatch.setattr(settings, "register_rate_window", 3600)
        for i in range(2):
            register(_register_req(f"{_UID_PREFIX}_rl{i}"), _ns(client=_ns(host="127.0.0.1")))
            _delete_user(f"{_UID_PREFIX}_rl{i}")
        with pytest.raises(HTTPException) as e:
            register(_register_req(f"{_UID_PREFIX}_rl2"), _ns(client=_ns(host="127.0.0.1")))
        assert e.value.status_code == 429
        assert e.value.detail["code"] == "rate_limited"

    def test_register_duplicate_409(self, monkeypatch):
        from types import SimpleNamespace as _ns
        monkeypatch.setattr(settings, "auth_allow_register", True)
        uname = f"{_UID_PREFIX}_dup"
        try:
            first = register(_register_req(uname), _ns(client=_ns(host="127.0.0.1")))
            assert first.code == 201
            with pytest.raises(HTTPException) as e:
                register(_register_req(uname), _ns(client=_ns(host="127.0.0.1")))
            assert e.value.status_code == 409
            assert e.value.detail["code"] == "username_exists"
        finally:
            _delete_user(uname)


# ============================================
# 管理员
# ============================================
class TestAdmin:
    def test_require_admin_forbidden(self):
        with pytest.raises(HTTPException) as e:
            require_admin(CurrentUser(username="u", role="user", is_active=True, token_version=1))
        assert e.value.status_code == 403

    def test_require_admin_ok(self):
        cu = require_admin(CurrentUser(username="u", role="admin", is_active=True, token_version=1))
        assert cu.role == "admin"

    def test_admin_disable_user(self):
        admin = f"{_UID_PREFIX}_adm"
        victim = f"{_UID_PREFIX}_vic"
        _create_user(admin, "adminpass123", "admin")
        _create_user(victim, "password123")
        try:
            victim_token = create_session_token(victim, 1)
            assert get_current_user(_fake_req(victim_token)).username == victim
            victim_id = None
            with get_db_session() as db:
                victim_id = db.execute(text("SELECT id FROM users WHERE username=:u"), {"u": victim}).scalar_one()
            cu_admin = CurrentUser(username=admin, role="admin", is_active=True, token_version=1)
            update_user(victim_id, UserUpdateRequest(is_active=False), admin=cu_admin)
            # victim 旧 token 失效
            with pytest.raises(HTTPException) as e:
                get_current_user(_fake_req(victim_token))
            assert e.value.status_code == 401
            assert e.value.detail["code"] == "disabled"
        finally:
            _delete_user(admin)
            _delete_user(victim)


# ============================================
# 登出清 Cookie（方舟 REOPENED 缺陷回归）
# ============================================
class TestLogoutClearsCookie:
    def test_logout_emits_clearing_set_cookie(self):
        out = logout(Response())
        assert out.status_code == 204
        set_cookie = out.headers.get("set-cookie", "")
        assert settings.auth_cookie_name in set_cookie
        assert "max-age=0" in set_cookie.lower()

    def test_logout_all_emits_clearing_set_cookie(self):
        uname = f"{_UID_PREFIX}_la"
        _create_user(uname, "password123")
        try:
            cu = CurrentUser(username=uname, role="user", is_active=True, token_version=1)
            out = logout_all(Response(), current_user=cu)
            assert out.status_code == 204
            assert settings.auth_cookie_name in out.headers.get("set-cookie", "")
            assert _token_version(uname) == 2  # 踢所有设备
        finally:
            _delete_user(uname)


# ============================================
# 防自锁兜底
# ============================================
class TestAntiSelfLock:
    def test_cannot_disable_self(self):
        uname = f"{_UID_PREFIX}_self1"
        _create_user(uname, "password123", "admin")
        try:
            cu = CurrentUser(username=uname, role="admin", is_active=True, token_version=1)
            with pytest.raises(HTTPException) as e:
                update_user(_user_id(uname), UserUpdateRequest(is_active=False), admin=cu)
            assert e.value.status_code == 400
            assert e.value.detail["code"] == "cannot_modify_self"
        finally:
            _delete_user(uname)

    def test_cannot_demote_self(self):
        uname = f"{_UID_PREFIX}_self2"
        _create_user(uname, "password123", "admin")
        try:
            cu = CurrentUser(username=uname, role="admin", is_active=True, token_version=1)
            with pytest.raises(HTTPException) as e:
                update_user(_user_id(uname), UserUpdateRequest(role="user"), admin=cu)
            assert e.value.status_code == 400
            assert e.value.detail["code"] == "cannot_modify_self"
        finally:
            _delete_user(uname)

    def test_invalid_role_rejected(self):
        uname = f"{_UID_PREFIX}_self3"
        _create_user(uname, "password123")
        try:
            cu = CurrentUser(username=f"{_UID_PREFIX}_adm9", role="admin", is_active=True, token_version=1)
            with pytest.raises(HTTPException) as e:
                update_user(_user_id(uname), UserUpdateRequest(role="superuser"), admin=cu)
            assert e.value.status_code == 400
            assert e.value.detail["code"] == "bad_format"
        finally:
            _delete_user(uname)


# ============================================
# get_current_user DB 故障 → 503
# ============================================
class TestDbFailure:
    def test_db_failure_returns_503(self, monkeypatch):
        token = create_session_token("someone", 1)

        def _boom(*args, **kwargs):
            raise SQLAlchemyError("connection down")

        monkeypatch.setattr("core.api.dependencies.get_db_session", _boom)
        import core.api.dependencies as deps
        # 直接构造真实 Request 以复现依赖模块路径查找
        from starlette.requests import Request
        req = Request(scope={"type": "http", "method": "GET", "path": "/x",
                             "headers": [], "server": ("x", 0), "client": ("127.0.0.1", 1),
                             "query_string": b"", "scheme": "http"})
        req._cookies = {"access_token": token}
        with pytest.raises(HTTPException) as e:
            get_current_user(req)
        assert e.value.status_code == 503
        assert e.value.detail["code"] == "db_unavailable"