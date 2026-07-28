"""
统一异常分类体系

提供 PipelineError 异常类，支持错误严重级别、分类和上下文信息。
所有 ETL 管道脚本应使用此异常体系替代裸 Exception。
"""
from __future__ import annotations

import enum
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ErrorSeverity(enum.Enum):
    """错误严重级别"""
    FATAL = "fatal"       # 致命错误，流程必须终止
    ERROR = "error"       # 错误，当前步骤失败，但可继续后续步骤
    WARNING = "warning"   # 警告，部分数据缺失，不影响核心流程
    INFO = "info"         # 信息，记录异常但无需处理


class ErrorCategory(enum.Enum):
    """错误分类"""
    NETWORK = "network"           # 网络连接错误
    DATA_SOURCE = "data_source"   # 数据源不可用/返回异常
    DATABASE = "database"         # 数据库操作错误
    DATA_VALIDATION = "data_validation"  # 数据校验失败
    TIMEOUT = "timeout"           # 超时
    CONFIGURATION = "configuration"  # 配置错误
    INTERNAL = "internal"         # 内部逻辑错误


# 可重试的错误类别
RETRYABLE_CATEGORIES = {
    ErrorCategory.NETWORK,
    ErrorCategory.TIMEOUT,
    ErrorCategory.DATA_SOURCE,
}


class PipelineError(Exception):
    """管道异常基类，携带结构化的错误上下文"""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        detail: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.category = category
        self.detail = detail
        self.context = context or {}

    def is_retryable(self) -> bool:
        """判断该错误是否可重试"""
        return self.category in RETRYABLE_CATEGORIES

    def is_fatal(self) -> bool:
        """判断是否致命错误"""
        return self.severity == ErrorSeverity.FATAL

    def to_dict(self) -> dict[str, Any]:
        """转为结构化字典，便于日志记录"""
        return {
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "detail": self.detail,
            "context": self.context,
        }

    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}/{self.category.value}] {self.message}"]
        if self.detail:
            parts.append(f"  detail: {self.detail}")
        if self.context:
            parts.append(f"  context: {self.context}")
        return "\n".join(parts)


# ---- 便捷工厂函数 ----

def network_error(message: str, detail: str = "", **ctx) -> PipelineError:
    return PipelineError(message, ErrorSeverity.ERROR, ErrorCategory.NETWORK, detail, ctx)


def datasource_error(message: str, detail: str = "", **ctx) -> PipelineError:
    return PipelineError(message, ErrorSeverity.ERROR, ErrorCategory.DATA_SOURCE, detail, ctx)


def timeout_error(message: str, detail: str = "", **ctx) -> PipelineError:
    return PipelineError(message, ErrorSeverity.ERROR, ErrorCategory.TIMEOUT, detail, ctx)


def database_error(message: str, detail: str = "", **ctx) -> PipelineError:
    return PipelineError(message, ErrorSeverity.ERROR, ErrorCategory.DATABASE, detail, ctx)


def validation_error(message: str, detail: str = "", **ctx) -> PipelineError:
    return PipelineError(message, ErrorSeverity.ERROR, ErrorCategory.DATA_VALIDATION, detail, ctx)


def fatal_error(message: str, detail: str = "", **ctx) -> PipelineError:
    return PipelineError(message, ErrorSeverity.FATAL, ErrorCategory.INTERNAL, detail, ctx)


def log_error(err: PipelineError, logger_instance: logging.Logger = None) -> None:
    """根据错误严重级别记录日志"""
    lg = logger_instance or logger
    ctx_str = ", ".join(f"{k}={v}" for k, v in err.context.items()) if err.context else ""
    msg = f"{err.message}"
    if err.detail:
        msg += f" | {err.detail}"
    if ctx_str:
        msg += f" | {ctx_str}"

    if err.severity == ErrorSeverity.FATAL:
        lg.critical(msg)
    elif err.severity == ErrorSeverity.ERROR:
        lg.error(msg)
    elif err.severity == ErrorSeverity.WARNING:
        lg.warning(msg)
    else:
        lg.info(msg)