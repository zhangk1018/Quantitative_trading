"""pytdx 市场-代码前缀映射工具"""
import re
import pandas as pd
from typing import Dict, Any


def filter_stock_codes(df: pd.DataFrame, market_config: Dict[str, Any]) -> pd.DataFrame:
    """
    根据配置中的正则表达式过滤股票代码。
    排除债券、基金、指数、权证等非股票品种。
    """
    patterns = []
    stock_filter = market_config.get("security_list_filter", {})
    for pat in stock_filter.get("stock_patterns", []):
        patterns.append(re.compile(pat))

    if not patterns:
        return df

    mask = df["code"].apply(lambda c: any(p.match(str(c)) for p in patterns))
    return df[mask].copy()