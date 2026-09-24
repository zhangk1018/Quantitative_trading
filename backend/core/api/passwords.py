"""
passwords.py - 密码散列模块

用标准库 hashlib.pbkdf2_hmac 实现密码散列与校验（零第三方依赖，不改 requirements.txt）。
存储格式：`salt_hex$iterations$hash_hex`，校验时使用常量时间比较。
"""

import hashlib
import hmac
import os
from typing import Optional

_ITERATIONS = 210_000
_SALT_LEN = 16
_MIN_PASSWORD_LEN = 8


def hash_password(password: str) -> str:
    """散列密码，返回 `{salt_hex}$iterations${hash_hex}` 字符串。

    Args:
        password: 明文密码。

    Returns:
        含随机盐的散列字符串。
    """
    salt = os.urandom(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{salt.hex()}${_ITERATIONS}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码与已存散列是否匹配。

    Args:
        password: 待校验的明文密码。
        stored: 已存储的散列（`salt$iterations$hash` 格式）。

    Returns:
        匹配返回 True，否则 False。格式非法时也返回 False。
    """
    try:
        salt_hex, iter_str, hash_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        iterations = int(iter_str)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def password_meets_policy(password: Optional[str]) -> bool:
    """校验密码策略：最小长度 ≥8。

    Args:
        password: 待校验密码。

    Returns:
        满足策略返回 True，否则 False。
    """
    return bool(password) and isinstance(password, str) and len(password) >= 8