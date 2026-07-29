import type { IndicatorParams, SellStrategy } from './backtestTypes';
import { DEFAULT_INDICATOR_PARAMS, DEFAULT_BACKTEST_CONFIG } from './backtestTypes';

const STORAGE_KEY = 'backtest_defaults';

export interface BacktestDefaults {
  executionPrice: 'next_open' | 'next_close';
  maxDeferDays: number;
  /** 手续费率（小数，如 0.00015 = 万分之1.5） */
  feeRate: number;
  slippage: number;
  riskFreeRate: number;
  indicatorParams: IndicatorParams;
  /** 卖出策略 */
  sellStrategy: SellStrategy;
  /** 高点回落比例（trailing_stop），如 0.08 = 8% */
  trailingStopPct: number;
  /** ATR周期（atr_chandelier），默认14 */
  atrPeriod: number;
  /** ATR倍数（atr_chandelier），默认3 */
  atrMultiplier: number;
  /** 短期EMA周期（ema_cross），默认10 */
  emaShort: number;
  /** 长期EMA周期（ema_cross），默认30 */
  emaLong: number;
}

export const DEFAULT_BACKTEST_DEFAULTS: BacktestDefaults = {
  executionPrice: (DEFAULT_BACKTEST_CONFIG.executionPrice as 'next_open') ?? 'next_open',
  maxDeferDays: DEFAULT_BACKTEST_CONFIG.maxDeferDays ?? 3,
  feeRate: DEFAULT_BACKTEST_CONFIG.feeRate ?? 0,
  slippage: DEFAULT_BACKTEST_CONFIG.slippage ?? 0,
  riskFreeRate: DEFAULT_BACKTEST_CONFIG.riskFreeRate ?? 0.03,
  indicatorParams: { ...DEFAULT_INDICATOR_PARAMS },
  sellStrategy: (DEFAULT_BACKTEST_CONFIG.sellStrategy as SellStrategy) ?? 'trailing_stop',
  trailingStopPct: DEFAULT_BACKTEST_CONFIG.trailingStopPct ?? 0.08,
  atrPeriod: DEFAULT_BACKTEST_CONFIG.atrPeriod ?? 14,
  atrMultiplier: DEFAULT_BACKTEST_CONFIG.atrMultiplier ?? 3,
  emaShort: DEFAULT_BACKTEST_CONFIG.emaShort ?? 10,
  emaLong: DEFAULT_BACKTEST_CONFIG.emaLong ?? 30,
};

export function getBacktestDefaults(): BacktestDefaults {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_BACKTEST_DEFAULTS, indicatorParams: { ...DEFAULT_INDICATOR_PARAMS } };
    const parsed = JSON.parse(raw);
    return {
      executionPrice: parsed.executionPrice ?? DEFAULT_BACKTEST_DEFAULTS.executionPrice,
      maxDeferDays: parsed.maxDeferDays ?? DEFAULT_BACKTEST_DEFAULTS.maxDeferDays,
      feeRate: parsed.feeRate ?? DEFAULT_BACKTEST_DEFAULTS.feeRate,
      slippage: parsed.slippage ?? DEFAULT_BACKTEST_DEFAULTS.slippage,
      riskFreeRate: parsed.riskFreeRate ?? DEFAULT_BACKTEST_DEFAULTS.riskFreeRate,
      indicatorParams: { ...DEFAULT_INDICATOR_PARAMS, ...parsed.indicatorParams },
      sellStrategy: parsed.sellStrategy ?? DEFAULT_BACKTEST_DEFAULTS.sellStrategy,
      trailingStopPct: parsed.trailingStopPct ?? DEFAULT_BACKTEST_DEFAULTS.trailingStopPct,
      atrPeriod: parsed.atrPeriod ?? DEFAULT_BACKTEST_DEFAULTS.atrPeriod,
      atrMultiplier: parsed.atrMultiplier ?? DEFAULT_BACKTEST_DEFAULTS.atrMultiplier,
      emaShort: parsed.emaShort ?? DEFAULT_BACKTEST_DEFAULTS.emaShort,
      emaLong: parsed.emaLong ?? DEFAULT_BACKTEST_DEFAULTS.emaLong,
    };
  } catch {
    console.warn('[Backtest] 回测默认设置读取失败，使用默认值');
    return { ...DEFAULT_BACKTEST_DEFAULTS, indicatorParams: { ...DEFAULT_INDICATOR_PARAMS } };
  }
}

export function saveBacktestDefaults(defaults: BacktestDefaults): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults));
  } catch (e) {
    console.warn('Failed to save backtest defaults to localStorage', e);
  }
}

/** 手续费率转为万分之显示（如 0.00015 → 1.5） */
export function feeRateToDisplay(rate: number): number {
  return Math.round(rate * 10000 * 100) / 100;
}

/** 万分之显示转为手续费率（如 1.5 → 0.00015） */
export function displayToFeeRate(display: number): number {
  return display / 10000;
}