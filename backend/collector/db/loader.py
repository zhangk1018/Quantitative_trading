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
from typing import Dict, Optional

# 支持的市场（与 stock_daily_snapshot.market 列取值对齐）
SUPPORTED_MARKETS = ("cn", "hk", "us")

# 项目根目录（与 export_parquet.py 使用同一路径）
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_DAILY_DIR = _PROJECT_ROOT / "data" / "price" / "daily"


def default_parquet_path(market: str = "cn") -> str:
    """按市场返回默认 parquet 路径。

    cn 保持历史兼容路径 latest_quotes.parquet；
    hk / us 使用 latest_quotes_{market}.parquet（与 export_parquet.py 输出一致）。
    """
    if market == "cn":
        return str(_DAILY_DIR / "latest_quotes.parquet")
    return str(_DAILY_DIR / f"latest_quotes_{market}.parquet")


def _resolve_parquet_path(market: str) -> str:
    """解析指定市场的 parquet 路径。

    优先级：环境变量 PARQUET_PATH_{MARKET}（大写）> PARQUET_PATH（仅 cn 复用）> 默认路径。
    """
    m = market.strip().lower()
    env_override = os.getenv(f"PARQUET_PATH_{m.upper()}")
    # 兼容旧逻辑：cn 仍可用 PARQUET_PATH 覆盖
    if env_override is None and m == "cn":
        env_override = os.getenv("PARQUET_PATH")
    return env_override or default_parquet_path(m)


# 兼容旧代码：默认（cn）路径仍指向标准数据目录；PARQUET_PATH 环境变量可覆盖
PARQUET_PATH = _resolve_parquet_path("cn")

# 兼容旧代码：保存默认（cn）单例
_default_loader: "DataLoader" = None
# 按市场缓存的 loader 实例
_loader_cache: Dict[str, "DataLoader"] = {}


def _get_default_loader() -> "DataLoader":
    """获取默认（cn）的 DataLoader 单例"""
    global _default_loader
    if _default_loader is None:
        _default_loader = get_loader("cn")
    return _default_loader


def get_loader(market: str = "cn") -> "DataLoader":
    """按市场获取 DataLoader 实例（内部按市场缓存，重复调用复用同一实例）。

    Args:
        market: 市场标识（cn/hk/us），决定加载对应的 parquet 文件。

    Returns:
        已加载对应市场数据的 DataLoader 实例。
    """
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"不支持的市场: {market}（可选 {SUPPORTED_MARKETS}）")
    if market not in _loader_cache:
        _loader_cache[market] = DataLoader(market=market).load()
    return _loader_cache[market]


class DataLoader:
    """数据加载器包装类 - 推荐使用此类进行数据访问

    支持按市场加载：market='cn'/'hk'/'us' 各对应一份 parquet 文件。
    """

    def __init__(self, market: str = "cn"):
        """Args:
            market: 市场标识（cn/hk/us），cn 为默认并保持历史行为。
        """
        if market not in SUPPORTED_MARKETS:
            raise ValueError(f"不支持的市场: {market}（可选 {SUPPORTED_MARKETS}）")
        self.market = market
        self._parquet_path = _resolve_parquet_path(market)
        self._df = None
        self._trade_date = ""
        self._field_counts: dict | None = None
        self._parquet_mtime: float = 0  # 上次加载时 parquet 文件的 mtime

    @property
    def parquet_path(self) -> str:
        """当前 loader 对应的 parquet 文件路径。"""
        return self._parquet_path

    def _check_reload(self) -> None:
        """检测 parquet 文件是否已变更，是则自动重新加载"""
        try:
            current_mtime = os.path.getmtime(self._parquet_path)
            if current_mtime > self._parquet_mtime:
                self._do_load()
        except (FileNotFoundError, OSError):
            pass  # 文件暂时不可读，继续使用缓存数据

    def _do_load(self) -> None:
        """内部加载逻辑（不检查 mtime）"""
        self._df = pd.read_parquet(self._parquet_path)
        self._parquet_mtime = os.path.getmtime(self._parquet_path)
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
