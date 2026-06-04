#!/usr/bin/env python3
"""错误分类器模块 - 区分可重试与不可重试错误"""
import re
from typing import Tuple
from utils.logger import setup_logger

logger = setup_logger('error_classifier')


class ErrorType:
    """错误类型枚举"""
    RETRYABLE = 'retryable'           # 可重试
    NON_RETRYABLE = 'non_retryable'   # 不可重试
    UNKNOWN = 'unknown'               # 未知


class ErrorClassifier:
    """错误分类器 - 根据错误类型判断是否可重试"""
    
    # 可重试的错误模式（网络相关）
    RETRYABLE_PATTERNS = [
        # 网络超时
        r'timeout',
        r'time out',
        r'connection timed out',
        r'request timed out',
        
        # 限流/服务端忙
        r'429',  # Too Many Requests
        r'too many requests',
        r'rate limit',
        r'rate limiting',
        r'server busy',
        r'service unavailable',
        
        # 网络连接问题
        r'connection refused',
        r'connection reset',
        r'network unreachable',
        r'dns resolution failed',
        r'socket.error',
        r'http.client.RemoteDisconnected',
        
        # 服务端错误（5xx）
        r'500',  # Internal Server Error
        r'502',  # Bad Gateway
        r'503',  # Service Unavailable
        r'504',  # Gateway Timeout
        
        # 临时不可用
        r'temporary unavailable',
        r'temp unavailable',
        
        # 数据库锁/忙
        r'database is locked',
        r'deadlock',
    ]
    
    # 不可重试的错误模式（数据/逻辑相关）
    NON_RETRYABLE_PATTERNS = [
        # 数据解析失败
        r'parsing failed',
        r'parse error',
        r'invalid format',
        r'invalid data',
        r'unexpected format',
        
        # 数据为空
        r'no data',
        r'empty response',
        r'no records',
        r'no results',
        r'empty data',
        
        # 参数错误（4xx）
        r'400',  # Bad Request
        r'401',  # Unauthorized
        r'403',  # Forbidden
        r'404',  # Not Found
        
        # 认证/权限问题
        r'unauthorized',
        r'invalid token',
        r'permission denied',
        r'access denied',
        
        # 数据校验失败
        r'validation failed',
        r'invalid parameter',
        r'missing parameter',
        
        # 业务逻辑错误
        r'business error',
        r'logic error',
        r'not supported',
        
        # 本地错误
        r'file not found',
        r'ioerror',
        r'oserror',
    ]
    
    @classmethod
    def classify(cls, error: Exception) -> Tuple[str, str]:
        """
        分类错误类型
        
        Args:
            error: 异常对象
        
        Returns:
            (错误类型, 错误描述)
        """
        error_str = str(error).lower()
        error_type = ErrorType.UNKNOWN
        
        # 检查可重试模式
        for pattern in cls.RETRYABLE_PATTERNS:
            if re.search(pattern, error_str):
                error_type = ErrorType.RETRYABLE
                break
        
        # 如果不是可重试，检查不可重试模式
        if error_type == ErrorType.UNKNOWN:
            for pattern in cls.NON_RETRYABLE_PATTERNS:
                if re.search(pattern, error_str):
                    error_type = ErrorType.NON_RETRYABLE
                    break
        
        logger.debug(f"错误分类结果: {error_type} - {error_str}")
        return error_type, str(error)
    
    @classmethod
    def is_retryable(cls, error: Exception) -> bool:
        """
        判断错误是否可重试
        
        Args:
            error: 异常对象
        
        Returns:
            是否可重试
        """
        error_type, _ = cls.classify(error)
        return error_type == ErrorType.RETRYABLE
    
    @classmethod
    def should_retry(cls, error: Exception, retry_count: int, max_retries: int) -> bool:
        """
        判断是否应该重试
        
        Args:
            error: 异常对象
            retry_count: 当前重试次数
            max_retries: 最大重试次数
        
        Returns:
            是否应该重试
        """
        if retry_count >= max_retries:
            return False
        
        return cls.is_retryable(error)
    
    @classmethod
    def get_retry_delay(cls, retry_count: int, base_delay: int = 60) -> int:
        """
        获取重试延迟（指数退避）
        
        Args:
            retry_count: 当前重试次数
            base_delay: 基础延迟（秒）
        
        Returns:
            延迟秒数
        """
        # 指数退避: base_delay * (2^retry_count)，但不超过最大延迟
        max_delay = 300  # 最大5分钟
        delay = min(base_delay * (2 ** retry_count), max_delay)
        return delay


# 测试函数
if __name__ == '__main__':
    # 测试各种错误类型
    test_errors = [
        Exception('Connection timed out'),
        Exception('429 Too Many Requests'),
        Exception('503 Service Unavailable'),
        Exception('Parsing failed: invalid format'),
        Exception('404 Not Found'),
        Exception('No data available'),
        Exception('Database is locked'),
        Exception('Unknown error occurred'),
    ]
    
    print("错误分类测试:")
    for error in test_errors:
        error_type, desc = ErrorClassifier.classify(error)
        is_retryable = ErrorClassifier.is_retryable(error)
        print(f"  {desc}: {error_type} (可重试: {is_retryable})")
