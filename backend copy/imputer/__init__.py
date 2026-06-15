"""
backend/imputer - 数据补全与复权模块

【设计目标】
- 数据缺口 → 从数据源重新拉取（incomplete_handler.py）
- 缺失值 → 前向填充/插值（missing_handler.py）【严格禁止 bfill 防未来函数】
- 复权处理 → 前/后复权因子计算与应用（adjuster.py）

【避坑指南】
1. 绝对禁止 bfill/后向填充 → 会导致前视偏差
2. 价格用 ffill，成交量用 0
3. 复权仅影响 OHLC，不影响 volume/amount
4. adj_factor 必须有完整历史，否则不能正确复权
"""

from .missing_handler import (
    MissingValueFiller,
    fill_missing_prices,
    fill_missing_volume,
    ALLOWED_FILL_METHODS,
    FORBIDDEN_FILL_METHODS,
)

from .adjuster import (
    Adjuster,
    adjust_prices,
    load_adj_factors,
)

from .incomplete_handler import DataGapDetector, DataGapFiller


__all__ = [
    'MissingValueFiller',
    'fill_missing_prices',
    'fill_missing_volume',
    'ALLOWED_FILL_METHODS',
    'FORBIDDEN_FILL_METHODS',
    'Adjuster',
    'adjust_prices',
    'load_adj_factors',
    'DataGapDetector',
    'DataGapFiller',
]
