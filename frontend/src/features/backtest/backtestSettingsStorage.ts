import type { IndicatorParams, SellStrategy } from './backtestTypes';
import { DEFAULT_INDICATOR_PARAMS, DEFAULT_BACKTEST_CONFIG } from './backtestTypes';

const STORAGE_KEY = 'backtest_defaults';

export interface BacktestDefaults {
  executionPrice: 'next_open' | 'next_close';
  maxDeferDays: number;
  /** 手续费率（小数，如 0.00015 = 万分之1.5） */
  feeRate: number;
  slippage: number;
  /** 印花税率（小数，如 0.0005 = 万5，仅卖出收取） */
  stampDuty: number;
  /** 过户费率（小数，如 0.00001 = 十万分之一） */
  transferFee: number;
  /** 最低佣金（元），A股统一5元 */
  minCommission: number;
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

// ── 数值范围校验辅助 ──────────────────────────────────────────────────

/** 校验数值是否在指定范围内，非法时使用默认值并记录警告 */
function validateNum(value: unknown, defaultValue: number, min: number, max: number, label: string): number {
  if (typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max) {
    return value;
  }
  if (value !== undefined) {
    console.warn(`[Backtest] ${label} 值 ${String(value)} 超出范围 [${min}, ${max}]，使用默认值 ${defaultValue}`);
  }
  return defaultValue;
}

// ── 默认值 ────────────────────────────────────────────────────────────

export const DEFAULT_BACKTEST_DEFAULTS: BacktestDefaults = {
  executionPrice: (DEFAULT_BACKTEST_CONFIG.executionPrice as 'next_open') ?? 'next_open',
  maxDeferDays: DEFAULT_BACKTEST_CONFIG.maxDeferDays ?? 3,
  feeRate: DEFAULT_BACKTEST_CONFIG.feeRate || 0.00025,
  slippage: DEFAULT_BACKTEST_CONFIG.slippage || 0.0001,
  stampDuty: 0.0005,     // 万5（A股卖出印花税标准）
  transferFee: 0.00001,  // 十万分之一（中证登标准）
  minCommission: 5,      // A股最低佣金5元
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

    // indicatorParams 类型守卫：仅当存储中为有效对象时才合并，否则使用默认值
    const indicatorParams = (
      typeof parsed.indicatorParams === 'object' &&
      parsed.indicatorParams !== null &&
      !Array.isArray(parsed.indicatorParams)
    )
      ? { ...DEFAULT_INDICATOR_PARAMS, ...parsed.indicatorParams }
      : (() => {
          if (parsed.indicatorParams !== undefined) {
            console.warn('[Backtest] indicatorParams 格式错误，已忽略存储值，使用默认值');
          }
          return { ...DEFAULT_INDICATOR_PARAMS };
        })();

    return {
      executionPrice: parsed.executionPrice ?? DEFAULT_BACKTEST_DEFAULTS.executionPrice,
      maxDeferDays: validateNum(parsed.maxDeferDays, DEFAULT_BACKTEST_DEFAULTS.maxDeferDays, 0, 30, 'maxDeferDays'),
      feeRate: validateNum(parsed.feeRate, DEFAULT_BACKTEST_DEFAULTS.feeRate, 0, 0.01, 'feeRate'),
      slippage: validateNum(parsed.slippage, DEFAULT_BACKTEST_DEFAULTS.slippage, 0, 0.01, 'slippage'),
      stampDuty: validateNum(parsed.stampDuty, DEFAULT_BACKTEST_DEFAULTS.stampDuty, 0, 0.01, 'stampDuty'),
      transferFee: validateNum(parsed.transferFee, DEFAULT_BACKTEST_DEFAULTS.transferFee, 0, 0.001, 'transferFee'),
      minCommission: validateNum(parsed.minCommission, DEFAULT_BACKTEST_DEFAULTS.minCommission, 0, 100, 'minCommission'),
      riskFreeRate: validateNum(parsed.riskFreeRate, DEFAULT_BACKTEST_DEFAULTS.riskFreeRate, 0, 0.5, 'riskFreeRate'),
      indicatorParams,
      sellStrategy: parsed.sellStrategy ?? DEFAULT_BACKTEST_DEFAULTS.sellStrategy,
      trailingStopPct: validateNum(parsed.trailingStopPct, DEFAULT_BACKTEST_DEFAULTS.trailingStopPct, 0, 0.5, 'trailingStopPct'),
      atrPeriod: validateNum(parsed.atrPeriod, DEFAULT_BACKTEST_DEFAULTS.atrPeriod, 2, 200, 'atrPeriod'),
      atrMultiplier: validateNum(parsed.atrMultiplier, DEFAULT_BACKTEST_DEFAULTS.atrMultiplier, 0.1, 20, 'atrMultiplier'),
      emaShort: validateNum(parsed.emaShort, DEFAULT_BACKTEST_DEFAULTS.emaShort, 2, 200, 'emaShort'),
      emaLong: validateNum(parsed.emaLong, DEFAULT_BACKTEST_DEFAULTS.emaLong, 2, 200, 'emaLong'),
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