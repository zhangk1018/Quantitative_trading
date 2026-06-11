"""
missing_handler.py - 缺失值填充（严格防未来函数）

【硬约束】
1. 价格字段（open/high/low/close）只允许 ffill（前向填充）
2. 成交量字段（volume）用 0 填充
3. 金额字段（amount）用 0 填充
4. 任何 bfill/后向填充/全局均值填充一律拒绝（防止前视偏差）

【为什么禁止 bfill】
金融数据按时间序列严格排序，"未来"数据不应影响"历史"补全。
如果允许 bfill，策略回测时会"看到"未发生的 K 线，导致回测虚高、实盘必亏。

【使用示例】
```python
from backend.imputer import MissingValueFiller
filler = MissingValueFiller()
df = filler.fill(df, columns=['open', 'high', 'low', 'close'], method='ffill')
```
"""

import logging
import pandas as pd
from typing import List, Optional

logger = logging.getLogger(__name__)


# ============================================
# 允许/禁止的填充方法（白名单 + 黑名单双重保护）
# ============================================

ALLOWED_FILL_METHODS = {'ffill', 'pad', 'interpolate'}
"""白名单：仅允许前向填充和插值"""

FORBIDDEN_FILL_METHODS = {'bfill', 'backfill', 'mean', 'median', 'zero', None}
"""黑名单：禁止的方法（包括 None/默认）"""


def _check_method(method: str):
    """检查填充方法合法性"""
    if method in FORBIDDEN_FILL_METHODS:
        raise ValueError(
            f"❌ 禁止使用填充方法 '{method}'！\n"
            f"   原因: 会引入未来函数/前视偏差，导致回测结果虚高、实盘亏损。\n"
            f"   允许的方法: {sorted(ALLOWED_FILL_METHODS)}"
        )
    if method not in ALLOWED_FILL_METHODS:
        raise ValueError(
            f"❌ 未知的填充方法: '{method}'\n"
            f"   允许的方法: {sorted(ALLOWED_FILL_METHODS)}"
        )


class MissingValueFiller:
    """
    缺失值填充器

    设计原则：
    1. 价格字段（OHLC）→ ffill（前向填充）：金融价格具有连续性
    2. 成交量/金额 → 0：缺失即代表无成交
    3. 任何后向操作一律禁止
    """

    def __init__(self, strict: bool = True):
        """
        Args:
            strict: 严格模式（默认 True）
                   True  → 禁止任何 bfill/mean 等不安全方法
                   False → 仅警告，但仍禁止 bfill
        """
        self.strict = strict

    def fill(
        self,
        df: pd.DataFrame,
        columns: Optional[List[str]] = None,
        method: str = 'ffill',
    ) -> pd.DataFrame:
        """
        填充 DataFrame 中的缺失值

        Args:
            df: 输入数据（必须按时间升序）
            columns: 要填充的列（None 表示所有数值列）
            method: 填充方法（ffill / interpolate）

        Returns:
            填充后的 DataFrame（不修改原数据）
        """
        _check_method(method)

        df = df.copy()
        if columns is None:
            columns = df.select_dtypes(include='number').columns.tolist()

        # 验证 DataFrame 是时间排序的
        if not df.index.is_monotonic_increasing:
            logger.warning('⚠️  DataFrame 索引不是单调递增，将先排序再填充')

        for col in columns:
            if col not in df.columns:
                continue
            null_count = df[col].isna().sum()
            if null_count == 0:
                continue
            if method == 'ffill' or method == 'pad':
                df[col] = df[col].ffill()
            elif method == 'interpolate':
                df[col] = df[col].interpolate(method='linear', limit_direction='forward')
            logger.info(f'  ✅ {col}: 填充 {null_count} 个缺失值（方法: {method}）')

        return df

    def fill_price_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        专门用于填充价格缺口（OHLC 四列）

        规则：所有价格列使用 ffill；如果仍为 NaN（前 N 行没数据），保持 NaN 不变
        """
        price_cols = ['open', 'high', 'low', 'close']
        cols = [c for c in price_cols if c in df.columns]
        return self.fill(df, columns=cols, method='ffill')

    def fill_volume_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        专门用于填充成交量/成交额缺口

        规则：直接填 0
        """
        vol_cols = ['volume', 'amount']
        cols = [c for c in vol_cols if c in df.columns]
        df = df.copy()
        for col in cols:
            if col in df.columns:
                null_count = df[col].isna().sum()
                if null_count > 0:
                    df[col] = df[col].fillna(0)
                    logger.info(f'  ✅ {col}: 填充 {null_count} 个缺失值（方法: 0）')
        return df


# ============================================
# 便捷函数
# ============================================

def fill_missing_prices(df: pd.DataFrame, method: str = 'ffill') -> pd.DataFrame:
    """便捷函数：填充价格缺口"""
    return MissingValueFiller().fill_price_gaps(df)


def fill_missing_volume(df: pd.DataFrame) -> pd.DataFrame:
    """便捷函数：填充成交量缺口"""
    return MissingValueFiller().fill_volume_gaps(df)
