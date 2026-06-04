"""
loader.py — Data access layer for the stock screener backend.

Loads `latest_quotes.parquet` into memory once at startup via `load()`.
After `load()` is called, callers access data through three module globals:
  - `df`           : the full pandas DataFrame (5484 rows)
  - `trade_date`   : trading date string in YYYYMMDD format
  - `field_counts` : dict of {column_name: hit_count} for binary 0/1 indicator columns

Call `_check_loaded()` before accessing these globals if you want an explicit
RuntimeError instead of a silent None/empty-value failure.
"""

import os
import pandas as pd
from pathlib import Path

# 数据文件路径配置
# 优先级：1. 环境变量 PARQUET_PATH > 2. 默认路径
# 默认路径指向量化系统标准数据目录
PARQUET_PATH = os.getenv(
    "PARQUET_PATH",
    str(Path(__file__).parent.parent.parent.parent / "data" / "price" / "daily" / "latest_quotes.parquet"),
)

df: pd.DataFrame = None
trade_date: str = ""
field_counts: dict[str, int] = {}


def _check_loaded() -> None:
    """Raise RuntimeError if load() has not been called yet."""
    if df is None:
        raise RuntimeError(
            "loader.load() has not been called yet. "
            "Ensure load() is invoked at application startup."
        )


def load() -> None:
    """Load parquet into memory. Called once at startup."""
    global df, trade_date, field_counts

    df = pd.read_parquet(PARQUET_PATH)
    trade_date = str(df["trade_date"].iloc[0])

    # Only count integer binary (0/1) columns with these prefixes.
    # vol_ratio_5 is intentionally excluded — it is a continuous float ratio,
    # not a binary flag, so the dtype guard below already excludes it.
    binary_prefixes = ("pattern_", "break_high_", "consec_up_")
    binary_cols = [
        c for c in df.columns
        if c.startswith(binary_prefixes) and df[c].dtype in ("int64", "int32", "int8", "bool")
    ]
    field_counts = {c: int(df[c].sum()) for c in binary_cols}


# ============================================
# DataLoader 包装类（为 FastAPI 依赖注入提供类型安全接口）
# ============================================

class DataLoader:
    """数据加载器包装类"""

    def __init__(self):
        self._df = None
        self._trade_date = ""
        self._field_counts = {}

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            raise RuntimeError("数据未加载，请先调用 load()")
        return self._df

    @property
    def trade_date(self) -> str:
        if not self._trade_date:
            raise RuntimeError("交易日未设置，请先调用 load()")
        return self._trade_date

    @property
    def field_counts(self) -> dict[str, int]:
        if not self._field_counts:
            raise RuntimeError("字段计数未计算，请先调用 load()")
        return self._field_counts

    def load(self) -> "DataLoader":
        """加载数据，更新内部状态"""
        load()
        self._df = df
        self._trade_date = trade_date
        self._field_counts = field_counts
        return self
