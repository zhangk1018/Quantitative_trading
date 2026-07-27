"""统一重试装饰器 — 消除分散在多个模块中的重试逻辑。

提供单一重试入口，支持指数退避、可配置重试异常、连接重置回调、限流检测。

使用示例:
    from utils.retry import retry_on_error

    @retry_on_error(max_retries=3, exceptions=(ConnectionError, TimeoutError))
    def fetch_data(url):
        ...

    # 带连接重置
    @retry_on_error(max_retries=3, exceptions=(OperationalError,),
                    on_retry=reset_connection)
    def db_query():
        ...
"""

import time
import logging
import functools
from typing import Callable, Tuple, Type, Optional

logger = logging.getLogger(__name__)


def retry_on_error(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (ConnectionError, TimeoutError),
    on_retry: Optional[Callable[[], None]] = None,
    rate_limit_detector: Optional[Callable[[Exception], Optional[float]]] = None,
):
    """指数退避重试装饰器。

    Args:
        max_retries: 最大重试次数（不含首次执行）
        initial_delay: 初始延迟（秒）
        max_delay: 最大延迟上限（秒）
        backoff: 退避倍数
        exceptions: 可重试的异常类型元组
        on_retry: 每次重试前执行的回调（如重置连接）
        rate_limit_detector: 限流检测函数，接收异常返回等待秒数（None 表示不重试）

    Returns:
        装饰后的函数
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise
                    logger.warning(
                        f"⚠️  {func.__name__} 失败 (尝试 {attempt+1}/{max_retries+1}): {e}"
                    )
                    if on_retry:
                        try:
                            on_retry()
                        except Exception:
                            pass
                    # 限流检测：返回特定等待秒数
                    if rate_limit_detector:
                        wait = rate_limit_detector(e)
                        if wait is not None:
                            delay = wait
                    logger.info(f"    {delay:.1f}s 后重试...")
                    time.sleep(delay)
                    delay = min(delay * backoff, max_delay)
        return wrapper
    return decorator