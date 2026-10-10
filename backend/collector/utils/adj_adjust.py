#!/usr/bin/env python3
"""
港股/美股复权数据转换工具（协作单 30.0 V2 / M2；复权口径修复 协作单 45.0）

基于数据源返回的原始 OHLC + 复权 Close 生成入库所需的 `raw_*` / `adj_*` 列，
以及除权因子 `adj_factor` 与除权日 `factor_date`。

复权口径（协作单 45.0 实测订正）：
- 新浪港股 `adjust='hfq'` 是**仿射**口径而非乘性：`hfq = a * raw + b`
  （a=累计股本因子，如送股/拆股；b=累计现金分红等**加性**调整）。
  实测：碧桂园 02007 a≈1、b≈5.2415（raw 0.18 → hfq 5.42）；腾讯 00700 a=5、
  b≈278.93；汇丰 00005 a=4.2501、b≈375.31。
- 因此 `adj_factor = adj_close / close` 只在 b=0 时才等于真实复权倍率；对 b≠0 的
  标的（尤其低价股）该比值随行情逐日抖动，既会污染 adj_* 的相对关系，
  也会让「比值变化 >1% 即除权」的检测几乎每天都命中（碧桂园天天被标除权）。
- 修复方式：①复权 OHLC 优先直接采用数据源提供的复权列（最忠实，无需建模）；
  ②除权日检测改为按**自适应模型**（乘性 / 仿射）检测因子跳变，详见 `detect_factor_dates`。

入库口径：
- raw_* 原始价；adj_* 复权价；adj_factor = Adj Close / Close（保留历史字段语义）
- 前端若需前复权，由前端按最新 adj_factor 实时折算，后端不落库
"""
import sys
import os
import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger(__name__)

# 除权日检测参数（协作单 45.0）
FACTOR_JUMP_TOL = 0.003     # 仿射模型：偏移量 b 跳变 > 0.3%×复权价 视为除权事件
MULT_RATIO_TOL = 0.01       # 乘性模型：复权倍率相对变化 > 1% 视为除权事件（原口径）
FACTOR_MIN_ROWS = 8         # 样本不足不做检测（宁缺勿滥，避免短窗口噪声误标）
MAX_FLAG_RATIO = 0.2        # 标记占比上限护栏：超过即判定估计失准，整体不标（防误标风暴）
AFFINE_MARGIN = 0.5         # 仿射模型判定余量：离散度需优于乘性的一半才判仿射


def split_raw_adj(
    df: pd.DataFrame,
    keep: Tuple[str, ...] = ('open', 'high', 'low', 'close'),
) -> pd.DataFrame:
    """把原始列 + 复权列拆成 raw_* / adj_* 两组入库列。

    复权口径为**自适应仿射模型** `adj_x = a*raw_x + b`（协作单 45.0）：
    - `a`：该标的当前复权区间的**股本因子**（累计送股/拆股），由 `Adj Share`
      列透传（数据源按完整历史稳健估计）；缺省退化为当日倍率
      `Adj Close/Close`，此时 b=0、退化为原乘性口径（美股 qfq×锚点即此情形）；
    - `b = Adj Close − a*raw_close`：累计**加性**调整（现金分红等），未除权日恒定。

    O/H/L 复权价来源优先级：
    1. **数据源直供的复权 OHLC**（新浪港股 `adjust='hfq'` 的 open/high/low/close，
       列名 `adj_open/adj_high/adj_low`）——直接采用，最忠实；
    2. 否则按仿射式折算 `adj_x = a*raw_x + b`。

    修复背景：原实现统一用 `raw_x × (Adj Close/Close)`（隐含乘性）。对仿射标的
    （hfq 含加性偏移）该倍率 = `a + b/close` 并非真实复权倍率，使复权 O/H/L 的
    日内波幅被放大 `(a + b/close)/a` 倍（实测碧桂园 02007 a≈1、b≈5.24 → ~30 倍；
    汇丰 00005 ~1.61 倍；腾讯 00700 ~1.13 倍），而 `adj_close`/`pre_close` 正确。

    Args:
        df: 含 Open/High/Low/Close/Adj Close 的 DataFrame（也可传已转小写的列名）；
            可含 `Adj Share`（股本因子）与 `Adj Open/Adj High/Adj Low`（直供复权价）
        keep: 需要拆分出 raw_/adj_ 的价格列（小写）

    Returns:
        新 DataFrame：
          raw_open/raw_high/raw_low/raw_close     原始价
          adj_open/adj_high/adj_low/adj_close     复权价
          adj_factor                              复权倍率 (Adj Close / Close，兼容字段)
          adj_share                               本行采用的股本因子 a（供增量快照复用）
          其余列透传（volume 等）
    """
    out = df.copy()
    # 统一列名（兼容大写/小写；含数据源直供的复权 OHLC 与股本因子）
    ren = {}
    for c in ['open', 'high', 'low', 'close',
              'adj close', 'adj open', 'adj high', 'adj low', 'adj share']:
        target = c.replace(' ', '_')
        for existing in out.columns:
            if existing.lower() == c:
                ren[existing] = target
                break
    if ren:
        out = out.rename(columns=ren)

    raw_cols = {k: f'raw_{k}' for k in keep}
    adj_cols = {k: f'adj_{k}' for k in keep}

    for k, raw in raw_cols.items():
        out[raw] = out.get(k)
    # 复权倍率（兼容字段，供质量监控/前端折算）：Adj Close / Close
    out['adj_factor'] = (out['adj_close'] / out['close']).fillna(1.0)
    # 股本因子 a：优先透传值，缺失则退化为当日倍率（= 乘性口径，b=0）
    share = (pd.to_numeric(out['adj_share'], errors='coerce')
             if 'adj_share' in out else pd.Series(np.nan, index=out.index, dtype=float))
    share = share.where(share > 0).fillna(out['adj_factor'])
    out['adj_share'] = share
    # 加性偏移 b = Adj Close − a*raw_close（乘性口径下恒为 0）
    offset = out['adj_close'] - share * out['close']

    for k, adj in adj_cols.items():
        synth = share * out.get(k) + offset
        source_col = out.get(f'adj_{k}')
        if source_col is not None:
            # 数据源直供复权价优先；个别缺失单元格按仿射式补
            out[adj] = source_col.where(source_col.notna(), synth)
        else:
            out[adj] = synth.round(4)

    # 小数精度规整
    for col in list(raw_cols.values()) + list(adj_cols.values()):
        if col in out:
            out[col] = out[col].round(4)
    return out


# ================================================================
# 前复权重建（协作单 45.0 订正：港股 hfq → 前复权 qfq）
# ================================================================
QFQ_MIN_FACTOR = 1e-4       # 单日因子下限守卫（防脏数据把因子压到 0/负）
QFQ_MAX_FACTOR = 1e4        # 单日因子上限守卫
QFQ_MIN_EVENT_ABS = 1e-4    # 事件识别绝对下限（原始价单位）
QFQ_MIN_EVENT_REL = 1e-3    # 事件识别相对下限（调整额 / 价格）：滤掉 4 位小数舍入噪声
QFQ_M_MIN = 0.01            # 累计倍率 M = Π_{s>t} (p−d)/p 下限守卫
QFQ_M_MAX = 1.0             # 上限：前复权累计倍率恒 ≤ 1（分红/折价配股只会让历史更便宜），
#                             超过 1 即模型/数据异常（仙股 b≫价格时噪声长链累积），截断为 1


def compute_qfq_prices(
    df: pd.DataFrame,
    price_cols: Tuple[str, ...] = ('open', 'high', 'low', 'close'),
) -> pd.DataFrame:
    """由库内 raw_*/adj_*/adj_share 精确重建**前复权** OHLC（协作单 45.0 订正）。

    背景：港股 `stock_quotes.close` 存的是新浪**后复权** hfq，且 hfq 为**仿射**口径
    `hfq = a·raw + b`（`a=adj_share` 股本因子、`b=累计加性调整`）。新浪前复权是
    **乘性**口径，二者不可互相换算（实测按仿射反解碧桂园 2016 得 -0.66，真值 2.27）。

    正确做法：把每个除权日的加性调整 `Δb` 还原为**每股调整额** `d = Δb / a`，
    再按乘性口径取「该日昨收 p 对应的因子 `f = (p − d) / p`」，累计后续所有因子即得
    前复权倍率：

        qfq_t = raw_t × Π_{s>t} f_s

    与新浪 `adjust='qfq'` 逐日对齐：实测碧桂园/腾讯/汇丰 2015 年至今误差 0
    （更早历史因配股/送股等复杂公司行动未建模，存在偏差，应用仅展示近 450 天）。

    Args:
        df: **单只股票**日线，按 trade_date 升序，需含
            `raw_open/raw_high/raw_low/raw_close/adj_close`，可选 `adj_share`
            （缺 `adj_share` 或缺全历史会退化为乘性近似）
        price_cols: 需要重建的价格列

    Returns:
        同 df，另加 `qfq_<col>`（前复权价，保留 4 位小数）与 `adj_cum`
        （累计因子 K_t = Π_{s≤t} f_s，锚定序列起点、追加式稳定）
    """
    out = df.copy().reset_index(drop=True)
    for c in price_cols:
        out[f'qfq_{c}'] = pd.to_numeric(out.get(f'raw_{c}'), errors='coerce')
    out['adj_cum'] = 1.0
    if out.empty or 'raw_close' not in out or 'adj_close' not in out:
        return out

    r = pd.to_numeric(out['raw_close'], errors='coerce').astype(float)
    h = pd.to_numeric(out['adj_close'], errors='coerce').astype(float)
    if 'adj_share' in out:
        a = pd.to_numeric(out['adj_share'], errors='coerce').astype(float)
    else:
        a = pd.Series(np.nan, index=out.index, dtype=float)
    a = a.where(a > 0).ffill().bfill().fillna(1.0)

    b = h - a * r                                  # 加性偏移量（未除权区间内恒定）
    db = b.diff()
    same_regime = a.eq(a.shift(1))                 # 股本因子未变（送股/拆股日不并入 b）
    d = (db / a).where(same_regime, 0.0)           # 当日每股调整额（原始价单位）
    p = r.shift(1)                                 # 昨收（原始价）
    # 事件门限：仙股（如 0007.HK raw≈0.03）的 4 位小数舍入误差会污染逐日 Δb，
    # 长链累积后使累计倍率爆掉（曾致 numeric 溢出）。仅当调整额达到价格的一定
    # 比例（且超过绝对下限）才视为真实除权事件；小额调整（<0.1% 价格）忽略不计。
    event = same_regime & (db.abs() > np.maximum(QFQ_MIN_EVENT_ABS, QFQ_MIN_EVENT_REL * p.abs()))
    f = ((p - d) / p).where(event.fillna(False), 1.0)
    f = f.where(np.isfinite(f) & (f > 0), 1.0)
    f = f.clip(QFQ_MIN_FACTOR, QFQ_MAX_FACTOR)

    cum = f.cumprod()                              # K_t = Π_{s≤t} f_s
    total = float(cum.iloc[-1]) if len(cum) else 1.0
    m = (total / cum).fillna(1.0).clip(QFQ_M_MIN, QFQ_M_MAX)   # M_t = Π_{s>t} f_s（末行 = 1）
    out['adj_cum'] = cum
    for c in price_cols:
        raw = pd.to_numeric(out.get(f'raw_{c}'), errors='coerce')
        out[f'qfq_{c}'] = (raw * m).round(4)
    return out


# ================================================================
# 除权日检测（协作单 45.0：自适应乘性 / 仿射模型）
# ================================================================
def estimate_share_factor(
    raw_close: pd.Series,
    adj_close: pd.Series,
    min_pairs: int = 5,
) -> Optional[float]:
    """稳健估计股本因子 a（仿射模型 adj = a*raw + b 的斜率）。

    取相邻交易日 `Δadj / Δraw` 的**中位数**，且仅使用 `|Δraw| ≥ 1% × raw` 的相邻对：
    小变动日 Δraw 与价格 tick 同量级，比值会被舍入噪声放大，必须剔除。

    Args:
        raw_close: 原始收盘价
        adj_close: 复权收盘价
        min_pairs: 有效相邻对下限，不足返回 None（调用方不得猜测）

    Returns:
        股本因子 a；样本不足或无效时返回 None
    """
    r = pd.to_numeric(raw_close, errors='coerce').astype(float)
    h = pd.to_numeric(adj_close, errors='coerce').astype(float)
    dr = r.diff()
    ratio = (h.diff() / dr)[dr.abs() >= r.abs() * 0.01]
    ratio = ratio[(ratio > 0) & np.isfinite(ratio)]
    if len(ratio) < min_pairs:
        return None
    return float(ratio.median())


def _model_dispersion(raw_close: pd.Series, adj_close: pd.Series) -> Tuple[float, float]:
    """返回 (乘性模型离散度, 仿射模型离散度)，用于选择复权口径模型。

    乘性口径（adj = 倍率 × raw）下 `adj/raw` 恒定；仿射口径（adj = a×raw + b）下
    `adj − a×raw` 恒定。取各自相邻日变化的中位数（对个别真实除权日稳健），
    归一化到价格量级后比较，离散度更小者即该标的的实际口径。
    """
    r = pd.to_numeric(raw_close, errors='coerce').astype(float)
    h = pd.to_numeric(adj_close, errors='coerce').astype(float)
    scale = float(h.abs().median()) if len(h) else 0.0
    ratio = (h / r).replace([np.inf, -np.inf], np.nan)
    d_mult = float((ratio.diff().abs() / ratio.abs()).median()) if len(ratio) else np.inf
    a = estimate_share_factor(r, h)
    if a is None or a <= 0 or not np.isfinite(a) or scale <= 0:
        return d_mult, np.inf
    d_affine = float((h - a * r).diff().abs().median()) / scale
    return d_mult, d_affine


def is_affine_model(raw_close: pd.Series, adj_close: pd.Series) -> bool:
    """判断标的复权口径更接近仿射（adj = a*raw + b）还是乘性（adj = k*raw）。

    判定要求仿射模型**显著更优**（离散度 < 乘性的一半才判仿射）：
    乘性口径（如美股 qfq×锚点、无除权的港股）在两模型下离散度都接近舍入噪声量级，
    此时必须留在乘性分支，否则一旦发生真实除权，仿射分支会因 a 用错而把新区间的
    `b = (k新 − a)·raw` 随行情漂移，产生额外误标。仿射标的（碧桂园 0207）两者
    相差 2~3 个数量级，余量充足。

    供 `detect_factor_dates` 统一口径使用，避免两处判定漂移。
    """
    d_mult, d_affine = _model_dispersion(raw_close, adj_close)
    return d_affine < d_mult * AFFINE_MARGIN


def _rolling_share_factor(raw: pd.Series, adj: pd.Series, window: int = 10) -> pd.Series:
    """逐日滚动估计股本因子 a_i（邻近 ±window 个有效相邻对的 Δadj/Δraw 中位数）。

    单一全局 a 无法覆盖「股本因子发生变化」的标的（送股/拆股，如腾讯 2014 年 5:1
    → 拆股前 a=1、拆股后 a=5），在少数 regime 段会因 a 用错而使偏移量 b 随行情漂移、
    产生大量伪跳变。滚动估计可自动跟随 regime 切换，为后续分段精修提供良好初值。
    """
    dr = raw.diff()
    dh = adj.diff()
    valid = dr.abs() >= raw.abs() * 0.01
    ratio = pd.Series(np.nan, index=raw.index, dtype=float)
    ratio[valid] = dh[valid] / dr[valid]
    ratio = ratio.replace([np.inf, -np.inf], np.nan).dropna()
    ratio = ratio[ratio > 0]
    if ratio.empty:
        return pd.Series(1.0, index=raw.index, dtype=float)
    rolled = ratio.rolling(window=2 * window + 1, center=True, min_periods=1).median()
    return rolled.reindex(raw.index).ffill().bfill().fillna(1.0)


def _refit_segments(raw: pd.Series, adj: pd.Series, edges, fallback: float,
                    min_rows: int = 10, min_pairs: int = 4) -> pd.Series:
    """按边界索引分段，逐段用段内样本稳健重估股本因子；段内样本不足则沿用邻段值。"""
    a = pd.Series(np.nan, index=raw.index, dtype=float)
    for pos in np.split(np.arange(len(raw)), edges):
        if len(pos) == 0:
            continue
        seg_a = None
        if len(pos) >= min_rows:
            seg_a = estimate_share_factor(
                raw.iloc[pos].reset_index(drop=True),
                adj.iloc[pos].reset_index(drop=True),
                min_pairs=min_pairs,
            )
        a.iloc[pos] = seg_a if (seg_a is not None and np.isfinite(seg_a) and seg_a > 0) else np.nan
    return a.ffill().bfill().fillna(fallback)


def _affine_jumps(raw: pd.Series, adj: pd.Series, valid: pd.Series,
                  share_hint: Optional[float], iterations: int = 3) -> Tuple[pd.Series, pd.Series]:
    """迭代求解仿射口径下偏移量 b 的跳变（= 除权除息事件）。

    流程：滚动估计逐日 a → 求 b 跳变 → 按跳变点分段 → 逐段稳健重估 a → 重复。
    迭代可让初值阶段的伪跳变收敛掉（收敛后段内 b 恒定，仅真实除权日跳变）。

    Returns:
        (jump_mask, share_factor_series)
    """
    fallback = share_hint if (share_hint and np.isfinite(share_hint) and share_hint > 0) else 1.0
    if len(raw) >= 30:
        a = _rolling_share_factor(raw, adj)
    else:
        # 短窗口（增量场景）：无法滚动估计，用数据源在完整历史上估的股本因子
        a = pd.Series(fallback, index=raw.index, dtype=float)

    def _jumps(a_series: pd.Series) -> pd.Series:
        jump = (adj - a_series * raw).diff().abs() > (adj.abs() * FACTOR_JUMP_TOL)
        return (jump & valid & valid.shift(1, fill_value=False)).fillna(False)

    jump = _jumps(a)
    for _ in range(iterations):
        a = _refit_segments(raw, adj, np.flatnonzero(jump.values), fallback)
        jump = _jumps(a)
    return jump, a


def detect_factor_dates(df: pd.DataFrame) -> pd.DataFrame:
    """标记除权除息生效日（factor_date）。

    修复协作单 45.0：原实现按 `adj_factor = adj_close/close` 的相对变化 >1% 判定除权，
    隐含「复权为乘性」假设。新浪港股 hfq 实为**仿射**口径（hfq = a*raw + b），对 b≠0
    的标的该比值随行情逐日抖动 → 几乎每天被判为除权（实测 1954 只港股中 1129 只
    有 >10% 的交易日被误标；碧桂园 02007 305 个交易日全部误标）。

    现按自适应模型检测**因子跳变**：
    - 仿射模型（`adj/raw` 随行情漂移，如港股：碧桂园 a=1/b≈5.24、腾讯 a=5/b≈279）：
      以 `b = adj − a*raw` 为不变量，`|Δb| > 0.3% × 复权价` 即视为除权；
    - 乘性模型（`adj/raw` 在区间内恒定，如美股 qfq×锚点）：保留原口径，
      比值相对变化 > 1% 即视为除权。

    另有两道保守护栏（协作单 45.0，防「误标风暴」这一事故形态本身）：
    - 样本 < `FACTOR_MIN_ROWS` 行不检测（短窗口噪声大，宁缺勿滥）；
    - 命中占比 > `MAX_FLAG_RATIO` 视为参数/口径失准，整体不标并告警。

    Args:
        df: 需含 `trade_date` / `raw_close` / `adj_close`（`split_raw_adj` 输出）；
            可含数据源直供的 `adj_share`（完整历史估计的股本因子，用于短窗口）

    Returns:
        同 df，另加列 factor_date：除权日填该日 trade_date，非除权日填 None
    """
    out = df.copy()
    out['factor_date'] = None
    if out.empty or 'trade_date' not in out or 'raw_close' not in out or 'adj_close' not in out:
        return out

    r = pd.to_numeric(out['raw_close'], errors='coerce').astype(float)
    h = pd.to_numeric(out['adj_close'], errors='coerce').astype(float)
    valid = r.notna() & h.notna() & (r > 0)
    if int(valid.sum()) < FACTOR_MIN_ROWS:
        return out

    rv, hv = r[valid], h[valid]
    d_mult, d_affine = _model_dispersion(rv, hv)
    use_affine = is_affine_model(rv, hv)

    if use_affine:
        # 股本因子优先用数据源在**完整历史**上估计并透传的值（短窗口下更可靠）
        share_hint: Optional[float] = None
        if 'adj_share' in out:
            share = pd.to_numeric(out['adj_share'], errors='coerce').dropna()
            if len(share) and share.iloc[0] > 0:
                share_hint = float(share.iloc[0])
        if share_hint is None:
            share_hint = estimate_share_factor(rv, hv)
        if share_hint is None and len(rv) < 30:
            return out  # 短窗口且无法获得股本因子 → 不标（宁缺勿滥）
        jump, _ = _affine_jumps(r, h, valid, share_hint)
    else:
        ratio = (h / r).replace([np.inf, -np.inf], np.nan)
        jump = ((ratio / ratio.shift(1) - 1.0).abs() > MULT_RATIO_TOL)

    jump = jump & valid & valid.shift(1, fill_value=False)
    jump = jump.fillna(False)

    n_flag = int(jump.sum())
    if n_flag and n_flag > MAX_FLAG_RATIO * int(valid.sum()):
        # 命中占比异常 → 口径/参数失准（正是本次事故形态），整体不标更安全
        logger.warning(
            "⚠️ 除权日检测命中占比异常（%d/%d），判定复权口径估计失准，"
            "本次不标注 factor_date（模型=%s，离散度 乘性=%.6f 仿射=%.6f）",
            n_flag, int(valid.sum()), '仿射' if use_affine else '乘性', d_mult, d_affine,
        )
        return out

    out['factor_date'] = out['trade_date'].where(jump)
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
    assert abs(res['adj_factor'].iloc[0] - 0.9) < 1e-9, res['adj_factor'].iloc[0]
    assert abs(res['adj_close'].iloc[0] - 90.0) < 1e-9, res['adj_close'].iloc[0]
    assert abs(res['adj_open'].iloc[0] - 90.0) < 1e-9
    # 第二日未除权：因子 110/110=1.0
    assert abs(res['adj_factor'].iloc[1] - 1.0) < 1e-9
    print("✅ split_raw_adj 单测通过")
