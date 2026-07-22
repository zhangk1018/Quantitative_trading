import type { IndicatorParams } from './backtestTypes';
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
}

export const DEFAULT_BACKTEST_DEFAULTS: BacktestDefaults = {
  executionPrice: (DEFAULT_BACKTEST_CONFIG.executionPrice as 'next_open') ?? 'next_open',
  maxDeferDays: DEFAULT_BACKTEST_CONFIG.maxDeferDays ?? 3,
  feeRate: DEFAULT_BACKTEST_CONFIG.feeRate ?? 0,
  slippage: DEFAULT_BACKTEST_CONFIG.slippage ?? 0,
  riskFreeRate: DEFAULT_BACKTEST_CONFIG.riskFreeRate ?? 0.03,
  indicatorParams: { ...DEFAULT_INDICATOR_PARAMS },
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
    };
  } catch {
    return { ...DEFAULT_BACKTEST_DEFAULTS, indicatorParams: { ...DEFAULT_INDICATOR_PARAMS } };
  }
}

export function saveBacktestDefaults(defaults: BacktestDefaults): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults));
}

/** 手续费率转为万分之显示（如 0.00015 → 1.5） */
export function feeRateToDisplay(rate: number): number {
  return Math.round(rate * 10000 * 100) / 100;
}

/** 万分之显示转为手续费率（如 1.5 → 0.00015） */
export function displayToFeeRate(display: number): number {
  return display / 10000;
}