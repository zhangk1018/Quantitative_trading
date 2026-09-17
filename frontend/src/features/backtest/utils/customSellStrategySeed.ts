/**
 * 自编卖出策略预置种子（初始化默认卖出策略）
 *
 * 改编自「策略回测」页签的两类卖出策略（K 2026-09-17 决策）：
 * - 调仓换股 ← 选股条件调仓（AST）的卖出逻辑
 * - 分层止盈 ← 选股条件分层止盈的卖出逻辑
 *
 * 自编卖出策略为「纯信号协议」：脚本对整段 K 线输出每日卖出信号（1=卖出, 0=持有），
 * 持仓上下文（成本/持仓天数/分批比例/选股条件）由回测引擎管理、脚本不可见，
 * 因此改编聚焦于可仅凭 OHLCV 表达的卖出触发信号。
 *
 * 在 SellStrategyManager 挂载时调用，确保预置策略首次使用时自动就绪。
 * 遵循幂等设计：名称已存在（含软删除记录）时跳过，不重复写入，删除后不复活。
 */

import {
  saveCustomSellStrategy,
  listAllCustomSellStrategies,
  MOCK_USER_ID,
} from './customSellStrategyStorage';

// =====================================================================
// 调仓换股 — 改编自「选股条件调仓（AST）」
// 原策略卖出逻辑：调仓日重新评估选股条件，持仓股条件不满足即换出（rebalance），
// 另附止损 -8% / 止盈 +25% / 超时平仓。改编为技术条件走弱即换出的纯信号。
// =====================================================================

const SELL_FORMULA_REBALANCE = `import numpy as np

def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    """选股条件调仓(AST)改编：持仓股技术条件走弱(趋势破坏)即换出
    任一触发即输出 1（卖出换股），否则 0（持有）：
    1. 收盘跌破 MA20（中期趋势走弱）
    2. MACD 死叉（DIF 下穿 DEA）
    3. 单日跌幅 >= 6%（急跌离场）
    """
    close = np.array(close_prices, dtype=float)
    n = len(close)
    if n < 30:
        return [0] * n

    # 滚动 SMA
    def rolling_sma(arr, window):
        out = np.full(n, np.nan)
        cumsum = np.cumsum(np.where(np.isnan(arr), 0, arr))
        cnt = np.cumsum(~np.isnan(arr))
        for i in range(window - 1, n):
            if cnt[i] >= window:
                out[i] = (cumsum[i] - (cumsum[i - window] if i >= window else 0)) / window
        return out

    # EMA（递推）
    def ema(arr, period):
        out = np.full(n, np.nan)
        alpha = 2.0 / (period + 1)
        s = 0
        while s < n and np.isnan(arr[s]):
            s += 1
        if s >= n:
            return out
        out[s] = arr[s]
        for j in range(s + 1, n):
            if np.isnan(arr[j]):
                out[j] = out[j - 1]
            else:
                out[j] = alpha * arr[j] + (1 - alpha) * out[j - 1]
        return out

    ma20 = rolling_sma(close, 20)
    dif = ema(close, 12) - ema(close, 26)
    dea = ema(dif, 9)

    # 单日跌幅
    prev_close = np.concatenate(([np.nan], close[:-1]))
    day_drop = (close - prev_close) / prev_close

    signal = np.zeros(n)
    signal[(close < ma20) | (dif < dea) | (day_drop <= -0.06)] = 1.0
    result = np.where(np.isnan(signal), 0, signal)
    return result.tolist()
`;

// =====================================================================
// 分层止盈 — 改编自「选股条件分层止盈」
// 原策略分层状态机（初始止损/TP1/TP2 分批止盈/保本/底仓无限续航）依赖持仓
// 成本与分层阶段，脚本不可见；改编保留「无限续航」底仓离场信号：
// =====================================================================

const SELL_FORMULA_LAYERED_TP = `import numpy as np

def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    """选股条件分层止盈改编：底仓「无限续航」离场信号
    任一触发即输出 1（卖出），否则 0（持有）：
    1. 近 20 日高点回撤 >= 4%（峰值回撤跟踪止盈）
    2. 收盘连续 2 天跌破 MA20（均线兜底）
    3. 单日跌幅 >= 6%（暴跌不等确认直接卖）
    """
    close = np.array(close_prices, dtype=float)
    high = np.array(high_prices, dtype=float)
    n = len(close)
    if n < 25:
        return [0] * n

    # 滚动 SMA
    def rolling_sma(arr, window):
        out = np.full(n, np.nan)
        cumsum = np.cumsum(np.where(np.isnan(arr), 0, arr))
        cnt = np.cumsum(~np.isnan(arr))
        for i in range(window - 1, n):
            if cnt[i] >= window:
                out[i] = (cumsum[i] - (cumsum[i - window] if i >= window else 0)) / window
        return out

    # 近 20 日最高价（近似持仓峰值）
    peak = np.full(n, np.nan)
    for i in range(19, n):
        peak[i] = np.max(high[i - 19:i + 1])

    ma20 = rolling_sma(close, 20)

    # 峰值回撤（负值表示回撤）
    drawdown = (close - peak) / peak

    # 单日跌幅
    prev_close = np.concatenate(([np.nan], close[:-1]))
    day_drop = (close - prev_close) / prev_close

    # 连续跌破 MA20 天数
    below_days = np.zeros(n)
    run = 0
    below = close < ma20
    for i in range(n):
        if below[i]:
            run += 1
        else:
            run = 0
        below_days[i] = run

    signal = np.zeros(n)
    signal[drawdown <= -0.04] = 1
    signal[below_days >= 2] = 1
    signal[day_drop <= -0.06] = 1
    result = np.where(np.isnan(signal), 0, signal)
    return result.tolist()
`;

/** 预置卖出策略列表（导出便于测试） */
export const PRESET_SELL_STRATEGIES = [
  {
    name: '调仓换股',
    formula: SELL_FORMULA_REBALANCE,
    operator: '>' as const,
    defaultThreshold: 0,
    description:
      '改编自策略回测「选股条件调仓(AST)」：持仓股技术条件走弱即换出（跌破MA20 / MACD死叉 / 单日跌≥6%）。原策略的止损-8%/止盈+25%/超时平仓需持仓上下文，由回测引擎管理。',
  },
  {
    name: '分层止盈',
    formula: SELL_FORMULA_LAYERED_TP,
    operator: '>' as const,
    defaultThreshold: 0,
    description:
      '改编自策略回测「选股条件分层止盈」：底仓无限续航离场信号（近20日高点回撤≥4% / 连续2天跌破MA20 / 单日跌≥6%）。分批止盈比例（TP1卖25%/TP2卖25%）由回测引擎分层状态机管理。',
  },
];

/**
 * 种子预置卖出策略（幂等，名称已存在——含软删除——时跳过）
 *
 * 在 SellStrategyManager 挂载时调用一次即可。
 * 软删除 = 用户彻底移除，刷新/重进页面不再自动种回。
 */
export function seedDefaultSellStrategies(userId: string = MOCK_USER_ID): void {
  const existing = listAllCustomSellStrategies(userId);
  for (const preset of PRESET_SELL_STRATEGIES) {
    if (existing.some((s) => s.name === preset.name)) {
      continue; // 已存在（含软删除记录），跳过
    }
    try {
      saveCustomSellStrategy({ ...preset }, userId);
      console.log(`[CustomSellStrategySeed] 预置卖出策略「${preset.name}」已初始化`);
    } catch (e) {
      // 并发写入时名称冲突可忽略（幂等保证）
      console.warn(`[CustomSellStrategySeed] 初始化「${preset.name}」失败（可能已存在）:`, e);
    }
  }
}
