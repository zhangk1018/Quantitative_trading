"""
通用重试装饰器

支持：
- 可配置重试次数、退避策略
- 仅对可恢复错误（网络/超时/数据源）重试
- 致命错误不重试，直接抛出
- 重试日志记录
"""
from __future__ import annotations

import functools
import logging
import time
import random
from typing import Callable, Type, Union, Tuple

from backend.utils.error_handler import PipelineError, ErrorSeverity, ErrorCategory

logger = logging.getLogger(__name__)

# 默认不可重试的异常类型
DEFAULT_NON_RETRYABLE: Tuple[Type[BaseException], ...] = (
    NotImplementedError,
    ModuleNotFoundError,
    ImportError,
    SyntaxError,
    TypeError,
    ValueError,
    AttributeError,
    KeyError,
    IndexError,
    SystemExit,
    KeyboardInterrupt,
)


def is_retryable_error(exc: BaseException) -> bool:
    """判断异常是否可重试"""
    # PipelineError 由自身判断
    if isinstance(exc, PipelineError):
        return exc.is_retryable()

    # 致命严重级别的 PipelineError 不可重试
    if isinstance(exc, PipelineError) and exc.is_fatal():
        return False

    # 默认不可重试的异常类型
    if isinstance(exc, DEFAULT_NON_RETRYABLE):
        return False

    # 网络/连接类异常可重试
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    return False


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    on_retry: Callable = None,
):
    """
    重试装饰器

    Args:
        max_attempts: 最大尝试次数（含首次）
        base_delay: 基础延迟秒数
        max_delay: 最大延迟秒数
        backoff_factor: 退避倍数
        jitter: 是否添加随机抖动
        on_retry: 重试回调函数，签名为 (exception, attempt, max_attempts) -> None

    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # 判断是否可重试
                    if not is_retryable_error(e):
                        logger.warning(
                            f"不可重试错误，直接抛出: {type(e).__name__}: {e}"
                        )
                        raise

                    # 最后一次尝试，不再重试
                    if attempt >= max_attempts:
                        logger.error(
                            f"重试 {max_attempts} 次后仍失败: {type(e).__name__}: {e}"
                        )
                        raise

                    # 计算延迟
                    delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    if jitter:
                        delay *= random.uniform(0.5, 1.5)

                    logger.warning(
                        f"尝试 {attempt}/{max_attempts} 失败: {type(e).__name__}: {e}. "
                        f"{delay:.1f}s 后重试..."
                    )

                    if on_retry:
                        try:
                            on_retry(e, attempt, max_attempts)
                        except Exception:
                            pass

                    time.sleep(delay)

            # 理论上不会到这里，但安全起见
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
):
    """异步版本的重试装饰器"""
    import asyncio

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if not is_retryable_error(e):
                        logger.warning(
                            f"不可重试错误，直接抛出: {type(e).__name__}: {e}"
                        )
                        raise

                    if attempt >= max_attempts:
                        logger.error(
                            f"重试 {max_attempts} 次后仍失败: {type(e).__name__}: {e}"
                        )
                        raise

                    delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    if jitter:
                        delay *= random.uniform(0.5, 1.5)

                    logger.warning(
                        f"尝试 {attempt}/{max_attempts} 失败: {type(e).__name__}: {e}. "
                        f"{delay:.1f}s 后重试..."
                    )

                    await asyncio.sleep(delay)

            if last_exception:
                raise last_exception

        return wrapper
    return decorator