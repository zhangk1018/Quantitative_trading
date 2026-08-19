"""
security.py - 认证安全模块

单密钥门禁 + HttpOnly Cookie 的核心安全原语：
- 门禁密钥时序安全比对（hmac.compare_digest）
- JWT 会话 token 签发/校验（python-jose，HS256）
- HttpOnly Cookie 签发/清除
"""

import hmac
from datetime import datetime, timedelta, timezone

from fastapi import Response
from jose import jwt, JWTError

from core.api.config import settings

_ALGORITHM = "HS256"


def verify_access_key(provided: str) -> bool:
    """时序安全比对门禁访问密钥。"""
    if not settings.access_key or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), settings.access_key.encode("utf-8"))


def create_session_token() -> str:
    """签发 JWT 会话 token（仅含过期时间，密钥不落 token）。"""
    if not settings.session_secret:
        raise ValueError("API_SESSION_SECRET 未配置，无法签发会话")
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.auth_cookie_max_age)
    payload = {"exp": expire}
    return jwt.encode(payload, settings.session_secret, algorithm=_ALGORITHM)


def decode_session_token(token: str) -> dict:
    """校验 JWT，返回 payload；失败抛 JWTError。"""
    return jwt.decode(token, settings.session_secret, algorithms=[_ALGORITHM])


def set_session_cookie(response: Response, token: str) -> None:
    """签发 HttpOnly 会话 Cookie。"""
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_cookie_max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """清除会话 Cookie。"""
    response.set_cookie(
        key=settings.auth_cookie_name,
        value="",
        max_age=0,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )