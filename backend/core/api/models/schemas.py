"""
schemas.py - API 数据模型（已迁移到 shared/schemas.py）

【迁移说明】
- 真实定义: ../../shared/schemas.py
- 本文件保留为向后兼容的 re-export 层
- 已有代码 `from backend.core.api.models.schemas import X` 继续工作
- 新代码请直接从 `from shared.schemas import X` 导入

【未来计划】
- v2.0: 删除此 re-export 层
"""

# 兼容层：原 `backend.core.api.models.schemas` 的所有公共符号都从这里 re-export
from shared.schemas import (
    # 模型类
    FilterField,
    FilterGroup,
    ScreenerRequest,
    ScreenerResponse,
    StockResponse,
    StocksRequest,
    ApiResponse,
    MetaResponse,
    KLineItem,
    KLineResponse,
    SignalItem,
    SignalResponse,
    # 从 constants 也 re-export 一下，方便旧代码
)

from shared.constants import (
    ListedBoard,
    ALLOWED_SORT_FIELDS,
)


__all__ = [
    'FilterField',
    'FilterGroup',
    'ScreenerRequest',
    'ScreenerResponse',
    'StockResponse',
    'StocksRequest',
    'ApiResponse',
    'MetaResponse',
    'KLineItem',
    'KLineResponse',
    'SignalItem',
    'SignalResponse',
    'ListedBoard',
    'ALLOWED_SORT_FIELDS',
]
