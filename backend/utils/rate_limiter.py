"""令牌桶频率限制器 — 统一管理 API 调用频率控制。

避免在 baostock.py 和 tushare.py 中重复定义 RateLimiter 类。
"""

import time
import threading


class RateLimiter:
    """令牌桶算法实现的频率限制器。

    Attributes:
        rate: 每秒生成的令牌数
        burst: 桶容量（最大令牌数）
    """

    def __init__(self, rate: float = 1.0, burst: int = 3):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self, timeout: float = None) -> bool:
        """获取一个令牌，阻塞直到获取成功或超时。

        Args:
            timeout: 最大等待时间（秒），None 表示无限等待

        Returns:
            True 表示获取成功，False 表示超时
        """
        start_time = time.time()
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                wait_time = (1 - self.tokens) / self.rate
            if timeout is not None:
                elapsed_total = time.time() - start_time
                if elapsed_total + wait_time > timeout:
                    return False
            # 使用 threading.Event 等待，支持线程中断（可被 KeyboardInterrupt 打断）
            threading.Event().wait(timeout=wait_time)