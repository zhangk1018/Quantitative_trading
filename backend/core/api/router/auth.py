"""
router/auth.py - 多用户账号体系认证路由

在原有「单密钥门禁 + HttpOnly Cookie」基础上升级为「用户名+密码多账号登录」。
- login/register/verify/config/output-all 为公开或按需鉴权
- 会话 token 携带 `sub`(username) + `ver`(token_version)
- 401 统一带 body `code` 区分语义（unauthenticated / bad_credentials / disabled）
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from core.api.config import settings
from core.api.passwords import hash_password, password_meets_policy, verify_password
from core.api.security import (
    clear_session_cookie,
    create_session_token,
    set_session_cookie,
)
from core.api.dependencies import CurrentUser, get_current_user, require_admin
from collector.db.database import get_db_session
from shared.schemas import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# 'default' 为老自选股归属保留名，禁止新用户注册占用（防止 bootstrap 误迁移）
_RESERVED_USERNAME = "default"

# ============================================
# 请求模型
# ============================================
class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(..., min_length=1, max_length=64, description="登录名")
    password: str = Field(..., min_length=1, description="登录密码")


class RegisterRequest(BaseModel):
    """注册请求体（需 auth_allow_register=true）。"""

    username: str = Field(..., min_length=1, max_length=64, description="登录名")
    password: str = Field(..., min_length=1, description="登录密码")
    display_name: Optional[str] = Field(None, max_length=64, description="显示名称")


class ChangePasswordRequest(BaseModel):
    """修改密码请求体（需校验旧密码）。"""

    old_password: str = Field(..., min_length=1, description="旧密码")
    new_password: str = Field(..., min_length=1, description="新密码")


class UserCreateRequest(BaseModel):
    """管理员建号请求体。"""

    username: str = Field(..., min_length=1, max_length=64, description="登录名")
    password: str = Field(..., min_length=1, description="登录密码")
    display_name: Optional[str] = Field(None, max_length=64, description="显示名称")
    role: str = Field("user", max_length=16, description="角色 admin|user")


class UserUpdateRequest(BaseModel):
    """管理员操作用户（重置密码 / 禁用启用 / 改角色）。"""

    password: Optional[str] = Field(None, description="重置密码")
    is_active: Optional[bool] = Field(None, description="是否启用")
    role: Optional[str] = Field(None, max_length=16, description="角色 admin|user")


# ============================================
# 注册限流（内存 dict + 滑动窗口，按 IP，重启清零，不引第三方组件）
# ============================================
_rate_records: dict = defaultdict(list)  # ip -> [timestamp, ...]


def _is_rate_limited(ip: Optional[str]) -> bool:
    """判断指定 IP 是否触发注册频率限制。"""
    if not ip:
        return False
    now = time.time()
    window = settings.register_rate_window
    limit = settings.register_rate_limit
    ts_list = _rate_records[ip]
    while ts_list and now - ts_list[0] > window:
        ts_list.pop(0)
    if len(ts_list) >= limit:
        return True
    ts_list.append(now)
    return False


def _username_ok(username: str) -> bool:
    """校验用户名合法性：非保留字、长度范围内。"""
    return username != _RESERVED_USERNAME


def _client_ip(request: Request) -> Optional[str]:
    """获取客户端 IP（注册限流用）。"""
    return request.client.host if request.client else None


# ============================================
# 公开接口
# ============================================
@router.post("/login", summary="登录")
def login(payload: LoginRequest, response: Response) -> ApiResponse[dict]:
    """校验用户名+密码，成功签发 HttpOnly 会话 Cookie 并返回身份。

    注意：login 不触发 token_version+1，避免多设备互相踢下线。
    """
    try:
        with get_db_session() as db:
            row = db.execute(
                sa_text("SELECT username, password_hash, role, is_active, token_version "
                        "FROM users WHERE username = :username"),
                {"username": payload.username},
            ).fetchone()
    except SQLAlchemyError as exc:
        logger.exception("[auth] login DB 查询失败")
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unavailable", "message": "认证服务暂时不可用，请稍后重试"},
        )
    if not row or not verify_password(payload.password, row[1]):
        raise HTTPException(
            status_code=401,
            detail={"code": "bad_credentials", "message": "用户名或密码错误"},
        )
    if not row[3]:
        raise HTTPException(
            status_code=403,
            detail={"code": "disabled", "message": "账号已被禁用，请联系管理员"},
        )
    username, role, token_version = row[0], row[2], int(row[4])
    # 签发携身份 token（ver = 当前版本）
    token = create_session_token(username, token_version)
    set_session_cookie(response, token)
    try:
        with get_db_session() as db:
            db.execute(
                sa_text("UPDATE users SET last_login_at = NOW() WHERE username = :username"),
                {"username": username},
            )
            db.commit()
    except SQLAlchemyError as exc:
        logger.exception("[auth] 更新 last_login_at 失败（不影响登录）")
    return ApiResponse(
        code=200,
        message="success",
        data={"username": username, "role": role},
    )


@router.get("/config", summary="认证配置（注册入口显隐）")
def auth_config() -> ApiResponse[dict]:
    """返回认证配置，前端据此显隐注册入口。"""
    return ApiResponse(
        code=200,
        message="success",
        data={"auth_allow_register": settings.auth_allow_register},
    )


@router.get("/verify", summary="会话探活")
def verify(request: Request) -> ApiResponse[dict]:
    """返回当前会话认证状态，用于前端初始化与路由守卫。"""
    if not settings.auth_enabled:
        return ApiResponse(code=200, message="success", data={"authenticated": True})
    try:
        cu = get_current_user(request)
    except HTTPException:
        cu = None
    if cu is None:
        return ApiResponse(code=200, message="success", data={"authenticated": False})
    return ApiResponse(
        code=200,
        message="success",
        data={"authenticated": True, "username": cu.username, "role": cu.role},
    )


@router.post("/register", summary="自助注册")
def register(payload: RegisterRequest, request: Request) -> ApiResponse[dict]:
    """按 auth_allow_register 开关开放自助注册，带 IP 限流。"""
    if not settings.auth_allow_register:
        raise HTTPException(
            status_code=403,
            detail={"code": "register_closed", "message": "未开放自助注册，请联系管理员"},
        )
    if _is_rate_limited(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "注册过于频繁，请稍后再试"},
        )
    if not _username_ok(payload.username):
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_format", "message": f"用户名 `{_RESERVED_USERNAME}` 为保留名，不可使用"},
        )
    if not password_meets_policy(payload.password):
        raise HTTPException(
            status_code=400,
            detail={"code": "weak_password", "message": "密码过短，至少需要 8 位"},
        )
    display_name = payload.display_name or payload.username
    try:
        with get_db_session() as db:
            db.execute(
                sa_text("INSERT INTO users (username, password_hash, display_name, role) "
                        "VALUES (:username, :password_hash, :display_name, 'user')"),
                {
                    "username": payload.username,
                    "password_hash": hash_password(payload.password),
                    "display_name": display_name,
                },
            )
            db.commit()
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail={"code": "username_exists", "message": "用户名已存在"},
        )
    except SQLAlchemyError as exc:
        logger.exception("[auth] register DB 写入失败")
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unavailable", "message": "认证服务暂时不可用，请稍后重试"},
        )
    return ApiResponse(
        code=201,
        message="success",
        data={"username": payload.username},
    )


# ============================================
# 需登录接口
# ============================================
@router.post("/logout", summary="退出登录")
def logout(response: Response) -> Response:
    """清除会话 Cookie（不触发 token_version+1）。

    注意：必须在 FastAPI 注入的 Response 上设置 status_code 并**原样返回**。
    若改为 `return Response(status_code=204)` 新建对象，注入对象上的
    `Set-Cookie`（清 Cookie）头会被丢弃 → 登出后 Cookie 未清、F5 仍回到应用内。
    """
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.post("/logout-all", summary="登出所有设备")
def logout_all(response: Response, current_user: CurrentUser = Depends(get_current_user)) -> Response:
    """触发 token_version+1，使该账号所有旧会话失效。"""
    try:
        with get_db_session() as db:
            db.execute(
                sa_text("UPDATE users SET token_version = token_version + 1 WHERE username = :username"),
                {"username": current_user.username},
            )
            db.commit()
    except SQLAlchemyError as exc:
        logger.exception("[auth] logout-all DB 更新失败")
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unavailable", "message": "认证服务暂时不可用，请稍后重试"},
        )
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", summary="当前用户信息")
def get_me(current_user: CurrentUser = Depends(get_current_user)) -> ApiResponse[dict]:
    """返回当前登录用户身份（顶栏展示当前用户用）。"""
    display_name = ""
    try:
        with get_db_session() as db:
            row = db.execute(
                sa_text("SELECT display_name FROM users WHERE username = :username"),
                {"username": current_user.username},
            ).fetchone()
            display_name = row[0] if row else ""
    except SQLAlchemyError:
        pass
    return ApiResponse(
        code=200,
        message="success",
        data={
            "username": current_user.username,
            "role": current_user.role,
            "display_name": display_name or current_user.username,
        },
    )


@router.post("/change-password", summary="修改密码")
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """校验旧密码后修改密码，并 token_version+1 使其他设备失效。"""
    if not password_meets_policy(payload.new_password):
        raise HTTPException(
            status_code=400,
            detail={"code": "weak_password", "message": "新密码过短，至少需要 8 位"},
        )
    try:
        with get_db_session() as db:
            row = db.execute(
                sa_text("SELECT password_hash FROM users WHERE username = :username"),
                {"username": current_user.username},
            ).fetchone()
            if not row or not verify_password(payload.old_password, row[0]):
                raise HTTPException(
                    status_code=401,
                    detail={"code": "bad_old_password", "message": "旧密码错误"},
                )
            db.execute(
                sa_text("UPDATE users SET password_hash = :hash, token_version = token_version + 1 "
                        "WHERE username = :username"),
                {"hash": hash_password(payload.new_password), "username": current_user.username},
            )
            db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("[auth] change-password DB 更新失败")
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unavailable", "message": "认证服务暂时不可用，请稍后重试"},
        )
    return Response(status_code=204)


# ============================================
# 管理员接口
# ============================================
@router.get("/users", summary="用户列表")
def list_users(_admin: CurrentUser = Depends(require_admin)) -> ApiResponse[list]:
    """返回所有用户（不含密码散列）。"""
    try:
        with get_db_session() as db:
            rows = db.execute(
                sa_text("SELECT id, username, display_name, role, is_active, token_version, "
                        "created_at, last_login_at FROM users ORDER BY id")
            ).fetchall()
    except SQLAlchemyError as exc:
        logger.exception("[auth] list-users DB 查询失败")
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unavailable", "message": "认证服务暂时不可用，请稍后重试"},
        )
    users = [
        {
            "id": r[0],
            "username": r[1],
            "display_name": r[2],
            "role": r[3],
            "is_active": r[4],
            "token_version": r[5],
            "created_at": str(r[6]) if r[6] else None,
            "last_login_at": str(r[7]) if r[7] else None,
        }
        for r in rows
    ]
    return ApiResponse(code=200, message="success", data=users)


@router.post("/users", summary="管理员建号")
def create_user(
    payload: UserCreateRequest,
    _admin: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """管理员创建新账号。"""
    role = payload.role if payload.role in ("admin", "user") else "user"
    if not password_meets_policy(payload.password):
        raise HTTPException(
            status_code=400,
            detail={"code": "weak_password", "message": "密码过短，至少需要 8 位"},
        )
    try:
        with get_db_session() as db:
            db.execute(
                sa_text("INSERT INTO users (username, password_hash, display_name, role) "
                        "VALUES (:username, :password_hash, :display_name, :role)"),
                {
                    "username": payload.username,
                    "password_hash": hash_password(payload.password),
                    "display_name": payload.display_name or payload.username,
                    "role": role,
                },
            )
            db.commit()
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail={"code": "username_exists", "message": "用户名已存在"},
        )
    except SQLAlchemyError as exc:
        logger.exception("[auth] create-user DB 写入失败")
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unavailable", "message": "认证服务暂时不可用，请稍后重试"},
        )
    return ApiResponse(code=201, message="success", data={"username": payload.username})


@router.put("/users/{user_id}", summary="管理员重置密码/禁用启用/改角色")
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    admin: CurrentUser = Depends(require_admin),
) -> ApiResponse[dict]:
    """更新用户：重置密码 / 禁用启用 / 改角色。重置或禁用时 token_version+1 使旧会话失效。

    含防自锁兜底：禁止禁用/降级当前登录账号；并保证系统至少保留 1 个启用状态的 admin。
    """
    if payload.password is not None and not password_meets_policy(payload.password):
        raise HTTPException(
            status_code=400,
            detail={"code": "weak_password", "message": "密码过短，至少需要 8 位"},
        )
    if payload.role is not None and payload.role not in ("admin", "user"):
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_format", "message": "角色仅支持 admin|user"},
        )
    bump_version = payload.password is not None or payload.is_active is False
    try:
        with get_db_session() as db:
            row = db.execute(
                sa_text("SELECT username FROM users WHERE id = :id"),
                {"id": user_id},
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "not_found", "message": "用户不存在"},
                )
            username = row[0]

            # 防自锁：禁止禁用/降级当前登录账号。
            # 该规则即保证了「系统至少保留 1 个启用状态 admin」——操作者本身必为启用 admin
            # （require_admin + is_active 已校验），其无法禁用/降级自己，故不可能清零。
            if username == admin.username:
                if payload.is_active is False:
                    raise HTTPException(
                        status_code=400,
                        detail={"code": "cannot_modify_self", "message": "不能禁用当前登录账号"},
                    )
                if payload.role is not None and payload.role != "admin":
                    raise HTTPException(
                        status_code=400,
                        detail={"code": "cannot_modify_self", "message": "不能降低当前登录账号的角色"},
                    )

            sets = []
            params = {"id": user_id}
            if payload.password is not None:
                sets.append("password_hash = :password_hash")
                params["password_hash"] = hash_password(payload.password)
            if payload.is_active is not None:
                sets.append("is_active = :is_active")
                params["is_active"] = payload.is_active
            if payload.role is not None:
                sets.append("role = :role")
                params["role"] = payload.role
            if bump_version:
                sets.append("token_version = token_version + 1")
            set_clause = ", ".join(sets)
            db.execute(
                sa_text(f"UPDATE users SET {set_clause} WHERE id = :id"),
                params,
            )
            db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("[auth] update-user DB 更新失败")
        raise HTTPException(
            status_code=503,
            detail={"code": "db_unavailable", "message": "认证服务暂时不可用，请稍后重试"},
        )
    return ApiResponse(code=200, message="success", data={"username": username})