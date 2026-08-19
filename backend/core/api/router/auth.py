"""
router/auth.py - 认证路由

单密钥门禁 + HttpOnly Cookie 会话管理：
- POST /api/auth/login   校验访问密钥，签发 HttpOnly Cookie
- POST /api/auth/logout  清除会话 Cookie
- GET  /api/auth/verify  探活当前会话是否已认证
"""

from fastapi import APIRouter, HTTPException, Request, Response
from jose import JWTError
from pydantic import BaseModel, Field

from core.api.config import settings
from core.api.security import (
    clear_session_cookie,
    create_session_token,
    decode_session_token,
    set_session_cookie,
    verify_access_key,
)
from shared.schemas import ApiResponse

router = APIRouter()


class LoginRequest(BaseModel):
    """登录请求体：门禁访问密钥。"""

    access_key: str = Field(..., min_length=1, description="门禁访问密钥")


@router.post("/login", summary="门禁登录")
def login(payload: LoginRequest, response: Response) -> ApiResponse[dict]:
    """校验访问密钥，成功后签发 HttpOnly 会话 Cookie。"""
    if not verify_access_key(payload.access_key):
        raise HTTPException(status_code=401, detail="访问密钥错误")
    token = create_session_token()
    set_session_cookie(response, token)
    return ApiResponse(
        code=200,
        message="success",
        data={"expire_in": settings.auth_cookie_max_age},
    )


@router.post("/logout", summary="退出登录")
def logout(response: Response) -> ApiResponse[None]:
    """清除会话 Cookie。"""
    clear_session_cookie(response)
    return ApiResponse(code=200, message="success", data=None)


@router.get("/verify", summary="会话探活")
def verify(request: Request) -> ApiResponse[dict]:
    """返回当前会话认证状态，用于前端初始化与路由守卫。"""
    if not settings.auth_enabled:
        return ApiResponse(code=200, message="success", data={"authenticated": True})
    token = request.cookies.get(settings.auth_cookie_name)
    authenticated = False
    if token:
        try:
            decode_session_token(token)
            authenticated = True
        except JWTError:
            authenticated = False
    return ApiResponse(
        code=200,
        message="success",
        data={"authenticated": authenticated},
    )