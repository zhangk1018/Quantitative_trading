#!/usr/bin/env python3
"""
港股/美股复权数据转换工具（协作单 30.0 V2 / M2）

基于 yfinance `auto_adjust=False` 的原始 OHLC + `Adj Close`（后复权）生成
入库所需的 `raw_*` / `adj_*` 列，以及除权因子 `adj_factor` 与除权日 `factor_date`。

口径（方案 §1.2 最终决策）：
- 后复权因子 back_factor = Adj Close / Close（每股成交价到当前价的比例系）
- 入库存原始价 raw_* + 后复权价 adj_*（adj_* 与原始价同源，仅 Close 用 Yahoo 的 Adj Close，
  Open/High/Low 按同一后复权因子折算：adj_price = raw_price * (Adj Close / Close)
- 前端若需前复权，由前端按最新 adj_factor 实时折算，后端不落库
"""
import sys
import os
from typing import Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def split_raw_adj(
    df: pd.DataFrame,
    keep: Tuple[str, ...] = ('open', 'high', 'low', 'close'),
) -> pd.DataFrame:
    """把 Yahoo 原生列（含 Close 与 Adj Close）拆成 raw_* / adj_* 两组入库列。

    Yahoo `auto_adjust=False` 返回：Open/High/Low/Close（原始）+ Adj Close（后复权）。
    这里 Open/High/Low 的后复权价按同一比率折算：adj = raw * (Adj Close / Close)。

    Args:
        df: 含 Open/High/Low/Close/Adj Close 的 DataFrame（也可传已转小写的列名）
        keep: 需要拆分出 raw_/adj_ 的价格列（小写）

    Returns:
        新 DataFrame：
          raw_open/raw_high/raw_low/raw_close     原始价（与 Yahoo Close/Open 一致）
          adj_open/adj_high/adj_low/adj_close     后复权价
          adj_factor                              后复权因子 (Adj Close / Close)
          其余列透传（volume 等）
    """
    out = df.copy()
    # 统一列名（兼容大写/小写）
    ren = {}
    for c in ['open', 'high', 'low', 'close', 'adj close']:
        for existing in out.columns:
            if existing.lower() == c:
                ren[existing] = c.replace(' ', '_')
                break
    if ren:
        out = out.rename(columns=ren)

    raw_cols = {k: f'raw_{k}' for k in keep}
    adj_cols = {k: f'adj_{k}' for k in keep}

    for k, raw in raw_cols.items():
        out[raw] = out.get(k)
    # 后复权因子：Adj Close / Close（未除权日恒为 1.0，除权日 <1）
    out['adj_factor'] = (out['adj_close'] / out['close']).fillna(1.0)
    for k, adj in adj_cols.items():
        # 原始价 × 后复权因子 → 后复权价
        out[adj] = (out.get(k) * out['adj_factor']).round(4)

    # 小数精度规整
    for col in list(raw_cols.values()) + list(adj_cols.values()):
        if col in out:
            out[col] = out[col].round(4)
    return out


def detect_factor_dates(df: pd.DataFrame) -> pd.DataFrame:
    """标记复权因子变化的除权日（factor_date）。

    当某日 adj_factor 与前一交易日不同（绝对值远离 1.0 或产生跳变），
    将该交易日标记为除权除息生效日（factor_date）。

    Args:
        df: 需含 trade_date 与 adj_factor（由 split_raw_adj 输出）

    Returns:
        同 df，另加列 factor_date：除权日填该日 trade_date，非除权日填 None
    """
    out = df.copy()
    if out.empty or 'adj_factor' not in out or 'trade_date' not in out:
        out['factor_date'] = None
        return out
    prev = out['adj_factor'].shift(1)
    # 因子相对变化明显（>1% 或 <99%）视为除权事件（忽略浮点噪声）
    change = (out['adj_factor'] / prev - 1.0).abs()
    is_factor_date = (change > 0.01).fillna(False)
    out['factor_date'] = out['trade_date'].where(is_factor_date)
    return out


if __name__ == '__main__':
    # 自测：用模拟数据验证拆分正确性
    import pandas as pd
    sample = pd.DataFrame({
        'Open': [100.0, 110.0],
        'High': [105.0, 115.0],
        'Low': [99.0, 109.0],
        'Close': [100.0, 110.0],
        'Adj Close': [90.0, 110.0],  # 前一天除权：因子 0.9
        'Volume': [1000, 2000],
    })
    res = split_raw_adj(sample)
    print("有效样例（模拟除权日 Adj Close=90, Close=100 → 因子0.9）:")
    print(res[['raw_close', 'adj_close', 'adj_factor']].to_string())
    # 验证：第一日因子 = 90/100 = 0.9；adj_close_open = 100*0.9=90
    import math
    assert abs(res['adj_factor'].iloc[0] - 0.9) < 1e-9, res['adj_factor'].iloc[0]
    assert abs(res['adj_close'].iloc[0] - 90.0) < 1e-9, res['adj_close'].iloc[0]
    assert abs(res['adj_open'].iloc[0] - 90.0) < 1e-9
    # 第二日未除权：因子 110/110=1.0
    assert abs(res['adj_factor'].iloc[1] - 1.0) < 1e-9
    print("✅ split_raw_adj 单测通过")