"""
loader.py — Data access layer for the stock screener backend.

Loads `latest_quotes.parquet` into memory via `DataLoader.load()`.
Automatically detects file modification and reloads when data changes,
so ETL pipeline updates are reflected without server restart.

After `load()` is called, callers access data through the `DataLoader` instance:
  - `loader.df`           : the full pandas DataFrame
  - `loader.trade_date`   : trading date string in YYYYMMDD format
  - `loader.field_counts` : dict of {column_name: hit_count} for binary 0/1 indicator columns

The module-level functions `get_df()`, `get_trade_date()`, `get_field_counts()`
are deprecated; use `DataLoader` instead.
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

# 兼容旧代码：保留全局变量作为单例模式的默认实例
_default_loader: "DataLoader" = None


def _get_default_loader() -> "DataLoader":
    """获取默认的 DataLoader 单例"""
    global _default_loader
    if _default_loader is None:
        _default_loader = DataLoader()
        _default_loader.load()
    return _default_loader


class DataLoader:
    """数据加载器包装类 - 推荐使用此类进行数据访问"""

    def __init__(self):
        self._df = None
        self._trade_date = ""
        self._field_counts: dict | None = None
        self._parquet_mtime: float = 0  # 上次加载时 parquet 文件的 mtime

    def _check_reload(self) -> None:
        """检测 parquet 文件是否已变更，是则自动重新加载"""
        try:
            current_mtime = os.path.getmtime(PARQUET_PATH)
            if current_mtime > self._parquet_mtime:
                self._do_load()
        except (FileNotFoundError, OSError):
            pass  # 文件暂时不可读，继续使用缓存数据

    def _do_load(self) -> None:
        """内部加载逻辑（不检查 mtime）"""
        self._df = pd.read_parquet(PARQUET_PATH)
        self._parquet_mtime = os.path.getmtime(PARQUET_PATH)
        self._trade_date = str(self._df["trade_date"].iloc[0])

        # Only count integer binary (0/1) columns with these prefixes.
        # vol_ratio_5 is intentionally excluded — it is a continuous float ratio,
        # not a binary flag, so the dtype guard below already excludes it.
        # 2026-06-16: 新增技术指标 pattern 列前缀
        binary_prefixes = (
            "pattern_", "break_high_", "consec_up_",
            "ma_long_", "ma_short_",
            "macd_low_", "macd_bottom_", "macd_high_", "macd_top_",
            "boll_break_",
            "rsi_low_", "rsi_high_", "rsi_top_", "rsi_bottom_",
        )
        binary_cols = [
            c for c in self._df.columns
            if c.startswith(binary_prefixes) and self._df[c].dtype in ("int64", "int32", "int8", "bool")
        ]
        self._field_counts = {c: int(self._df[c].sum()) for c in binary_cols}

    @property
    def df(self) -> pd.DataFrame:
        self._check_reload()
        if self._df is None:
            raise RuntimeError("数据未加载，请先调用 load()")
        return self._df

    @property
    def trade_date(self) -> str:
        self._check_reload()
        if not self._trade_date:
            raise RuntimeError("交易日未设置，请先调用 load()")
        return self._trade_date

    @property
    def field_counts(self) -> dict:
        self._check_reload()
        if self._field_counts is None:
            raise RuntimeError("字段计数未计算，请先调用 load()")
        return self._field_counts

    def load(self) -> "DataLoader":
        """加载数据，更新内部状态"""
        self._do_load()
        return self


# ============================================
# 兼容旧 API（建议迁移到 DataLoader）
# ============================================

def get_df() -> pd.DataFrame:
    """获取 DataFrame (已弃用，请使用 DataLoader.df)"""
    return _get_default_loader().df


def get_trade_date() -> str:
    """获取交易日期 (已弃用，请使用 DataLoader.trade_date)"""
    return _get_default_loader().trade_date


def get_field_counts() -> dict:
    """获取字段计数 (已弃用，请使用 DataLoader.field_counts)"""
    return _get_default_loader().field_counts


def _check_loaded() -> None:
    """Raise RuntimeError if load() has not been called yet."""
    loader = _get_default_loader()
    if loader._df is None:
        raise RuntimeError(
            "loader.load() has not been called yet. "
            "Ensure load() is invoked at application startup."
        )


def load() -> None:
    """Load parquet into memory. Called once at startup. (已弃用，请使用 DataLoader.load)"""
    _get_default_loader()
