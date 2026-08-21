/**
 * 自编指标种子数据（初始化默认指标）
 *
 * 在 ScreenerProvider 启动时调用，确保"8条件选股改进"指标首次使用时自动就绪。
 * 遵循幂等设计：已存在时跳过，不重复写入。
 */

import { saveCustomIndicator, listCustomIndicators, MOCK_USER_ID } from './customIndicatorStorage';

// =====================================================================
// 8条件选股改进 — 综合评分公式
// 每日评分 0-8 分，得分 ≥ 6 即满足条件
// =====================================================================

const FORMULA_8_CONDITION = `import numpy as np

def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    close = np.array(close_prices, dtype=float)
    high = np.array(high_prices, dtype=float)
    low = np.array(low_prices, dtype=float)
    open_p = np.array(open_prices, dtype=float)
    volume = np.array(volumes, dtype=float)

    n = len(close)
    if n < 50:
        return 0

    score = np.zeros(n)

    # ========== 辅助：滚动SMA ==========
    def rolling_sma(arr, window):
        out = np.full(n, np.nan)
        cumsum = np.nancumsum(np.where(np.isnan(arr), 0, arr))
        cnt = np.cumsum(~np.isnan(arr))
        for i in range(window - 1, n):
            if cnt[i] >= window:
                out[i] = (cumsum[i] - (cumsum[i - window] if i >= window else 0)) / window
        return out

    # ========== 辅助：EMA ==========
    def ema(arr, period):
        out = np.full(n, np.nan)
        alpha = 2.0 / (period + 1)
        valid_start = 0
        while valid_start < n and np.isnan(arr[valid_start]):
            valid_start += 1
        if valid_start >= n:
            return out
        out[valid_start] = arr[valid_start]
        for j in range(valid_start + 1, n):
            if np.isnan(arr[j]):
                out[j] = out[j-1]
            else:
                out[j] = alpha * arr[j] + (1 - alpha) * out[j-1]
        return out

    # ========== 1. RSI < 90 ==========
    rsi_period = 14
    deltas = np.diff(close, prepend=np.nan)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    sma_gain = rolling_sma(gains, rsi_period)
    sma_loss = rolling_sma(losses, rsi_period)

    rsi = np.full(n, 100.0)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid_rs = sma_loss > 0
        rsi[valid_rs] = 100.0 - 100.0 / (1.0 + sma_gain[valid_rs] / sma_loss[valid_rs])
    score[rsi < 90] += 1

    # ========== 2. 动量 > 1% ==========
    if n >= 2:
        momentum = np.full(n, np.nan)
        momentum[1:] = (close[1:] - close[:-1]) / close[:-1] * 100
        score[momentum > 1] += 1

    # ========== 3. 波动率 < 6% ==========
    if n >= 21:
        daily_ret = np.full(n, np.nan)
        daily_ret[1:] = (close[1:] - close[:-1]) / close[:-1]
        vol_arr = np.full(n, np.nan)
        for i in range(20, n):
            vol_arr[i] = np.std(daily_ret[i-19:i+1]) * 100
        score[vol_arr < 6] += 1

    # ========== 4. 成交量 > 20日均量 ==========
    vol_sma = rolling_sma(volume, 20)
    score[volume > vol_sma] += 1

    # ========== 5. ADX > 25（Wilder 平滑法） ==========
    if n >= 28:
        # 真实波幅 TR（从索引1开始）
        high_low = high[1:] - low[1:]
        high_close_c = np.abs(high[1:] - close[:-1])
        low_close_c = np.abs(low[1:] - close[:-1])
        tr = np.maximum(high_low, np.maximum(high_close_c, low_close_c))

        # 方向性移动
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        # ATR（Wilder 平滑）
        atr = np.full(len(tr), np.nan)
        atr[13] = np.mean(tr[:14])
        for i in range(14, len(tr)):
            atr[i] = (atr[i-1] * 13 + tr[i]) / 14

        # +DI / -DI
        plus_di = np.full(len(tr), np.nan)
        minus_di = np.full(len(tr), np.nan)
        plus_di[13] = np.sum(plus_dm[:14]) / np.sum(tr[:14]) * 100 if np.sum(tr[:14]) != 0 else 0
        minus_di[13] = np.sum(minus_dm[:14]) / np.sum(tr[:14]) * 100 if np.sum(tr[:14]) != 0 else 0
        for i in range(14, len(tr)):
            plus_di[i] = (plus_di[i-1] * 13 + (plus_dm[i] / atr[i] * 100 if atr[i] != 0 else 0)) / 14
            minus_di[i] = (minus_di[i-1] * 13 + (minus_dm[i] / atr[i] * 100 if atr[i] != 0 else 0)) / 14

        # DX
        dx = np.full(len(plus_di), np.nan)
        for i in range(13, len(plus_di)):
            denom = plus_di[i] + minus_di[i]
            dx[i] = np.abs(plus_di[i] - minus_di[i]) / denom * 100 if denom != 0 else 0

        # ADX（Wilder 平滑 DX）
        adx = np.full(len(dx), np.nan)
        adx[27] = np.mean(dx[14:28])
        for i in range(28, len(dx)):
            adx[i] = (adx[i-1] * 13 + dx[i]) / 14

        # 对齐到主索引（TR/ADX 起点偏移1）
        adx_aligned = np.full(n, np.nan)
        for j in range(27, len(adx)):
            adx_aligned[j + 1] = adx[j]
        score[adx_aligned > 25] += 1

    # ========== 6. 收盘价 > EMA50 ==========
    ema50 = ema(close, 50)
    score[close > ema50] += 1

    # ========== 7. 收盘价 > EMA200 ==========
    if n >= 200:
        ema200 = ema(close, 200)
        score[close > ema200] += 1

    # ========== 8. MACD > 信号线 ==========
    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    dif = ema12 - ema26
    dea = ema(dif, 9)
    score[dif > dea] += 1

    # 返回每日分数数组
    result = np.where(np.isnan(score), 0, score)
    return result.tolist()
`;

/**
 * 种子"8条件选股改进"指标（幂等，已存在时跳过）
 *
 * 在 ScreenerProvider 启动时调用一次即可。
 */
export function seed8ConditionIndicator(): void {
  const name = '8条件选股改进';
  const existing = listCustomIndicators(MOCK_USER_ID);
  if (existing.some((i) => i.name === name)) {
    return; // 已存在，跳过
  }

  try {
    saveCustomIndicator(
      {
        name,
        category: 'trend',
        syntax: 'python_talib',
        formula: FORMULA_8_CONDITION,
        params: [],
        operator: '>=',
        defaultThreshold: 6,
        description:
          '基于8个条件的综合选股评分系统：RSI<90、动量>1%、波动率<6%、成交量>20日均量、ADX>25、收盘价>EMA50、收盘价>EMA200、MACD>信号线。每日评分0-8分，得分≥6即满足条件。',
        visibility: 'private',
      },
      MOCK_USER_ID,
    );
    console.log('[CustomIndicatorSeed] 8条件选股改进 已初始化');
  } catch (e) {
    // 并发写入时 name 冲突可忽略（幂等保证）
    console.warn('[CustomIndicatorSeed] 初始化失败（可能已存在）:', e);
  }
}