// src/features/backtest/strategyBacktestSettingsStorage.ts
// 策略回测默认设置存储层 | 对应 V4 方案 Card 1-4

import type { StrategyBacktestDefaults } from './strategyBacktestTypes';

const STORAGE_KEY = 'strategy_backtest_defaults';

/**
 * 策略回测默认值（对照 V4 方案表格）
 * 注意：资金单位为分，费率使用小数表示
 */
export const DEFAULT_STRATEGY_BACKTEST_DEFAULTS: StrategyBacktestDefaults = {
  // ---------- Card 1: 基础参数 ----------
  initialCapital: 100_000_000, // 100万 = 100_000_000 分
  benchmarkCode: '000300.SH',
  benchmarkTotalReturn: false,
  riskFreeRate: 0.03, // 3%
  warmupDays: 60,

  // ---------- Card 2: 调仓与仓位 ----------
  rebalanceInterval: 5, // 每周（5个交易日）
  maxPositions: 10,
  positionAlloc: 'equal',
  singleStockMaxPct: 1.0, // 100% = 不限制
  idleCashReturn: 'none',
  idleCashRate: 0.02, // 2% 年化

  // ---------- Card 3: 交易成本 ----------
  feeRate: 0.00025, // 万2.5
  slippage: 0.0001, // 万1
  stampDuty: 0.001, // 千1
  minCommission: 500, // 5元 = 500分

  // ---------- Card 4: 风险控制（个股风控） ----------
  stopLossPct: -0.08, // -8%
  takeProfitPct: 0.25, // 25%
  maxHoldDays: 20,
  maxDeferDays: 3,
  deferFailAction: 'abandon',

  // ---------- Card 4: 组合级风控（默认关闭） ----------
  dailyLossLimitEnabled: false,
  dailyLossLimitPct: -0.05, // -5%
  maxDrawdownStopEnabled: false,
  maxDrawdownStopPct: -0.15, // -15%
};

/**
 * 读取策略回测默认设置
 * 若 localStorage 无数据或解析失败，返回默认值
 */
export function getStrategyBacktestDefaults(): StrategyBacktestDefaults {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS };
    const parsed = JSON.parse(raw);
    return {
      // Card 1
      initialCapital: parsed.initialCapital ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.initialCapital,
      benchmarkCode: parsed.benchmarkCode ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.benchmarkCode,
      benchmarkTotalReturn: parsed.benchmarkTotalReturn ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.benchmarkTotalReturn,
      riskFreeRate: parsed.riskFreeRate ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.riskFreeRate,
      warmupDays: parsed.warmupDays ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.warmupDays,
      // Card 2
      rebalanceInterval: parsed.rebalanceInterval ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.rebalanceInterval,
      maxPositions: parsed.maxPositions ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxPositions,
      positionAlloc: parsed.positionAlloc ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.positionAlloc,
      singleStockMaxPct: parsed.singleStockMaxPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.singleStockMaxPct,
      idleCashReturn: parsed.idleCashReturn ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.idleCashReturn,
      idleCashRate: parsed.idleCashRate ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.idleCashRate,
      // Card 3
      feeRate: parsed.feeRate ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.feeRate,
      slippage: parsed.slippage ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.slippage,
      stampDuty: parsed.stampDuty ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.stampDuty,
      minCommission: parsed.minCommission ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.minCommission,
      // Card 4
      stopLossPct: parsed.stopLossPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.stopLossPct,
      takeProfitPct: parsed.takeProfitPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.takeProfitPct,
      maxHoldDays: parsed.maxHoldDays ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxHoldDays,
      maxDeferDays: parsed.maxDeferDays ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxDeferDays,
      deferFailAction: parsed.deferFailAction ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.deferFailAction,
      dailyLossLimitEnabled: parsed.dailyLossLimitEnabled ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.dailyLossLimitEnabled,
      dailyLossLimitPct: parsed.dailyLossLimitPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.dailyLossLimitPct,
      maxDrawdownStopEnabled: parsed.maxDrawdownStopEnabled ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxDrawdownStopEnabled,
      maxDrawdownStopPct: parsed.maxDrawdownStopPct ?? DEFAULT_STRATEGY_BACKTEST_DEFAULTS.maxDrawdownStopPct,
    };
  } catch {
    return { ...DEFAULT_STRATEGY_BACKTEST_DEFAULTS };
  }
}

/**
 * 保存策略回测默认设置
 */
export function saveStrategyBacktestDefaults(defaults: StrategyBacktestDefaults): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults));
}

// ==================== 单位转换辅助函数 ====================

/** 分转元（如 10000000 → 100） */
export function fenToYuan(fen: number): number {
  return fen / 100;
}

/** 元转分（如 100 → 10000000） */
export function yuanToFen(yuan: number): number {
  return Math.round(yuan * 100);
}

/** 分转万元显示（如 10000000 → 100） */
export function fenToWanYuan(fen: number): number {
  return fen / 10000;
}

/** 万元转分（如 100 → 10000000） */
export function wanYuanToFen(wan: number): number {
  return Math.round(wan * 10000);
}

/** 手续费率转万分之显示（如 0.00025 → 2.5） */
export function feeRateToDisplay(rate: number): number {
  return Math.round(rate * 10000 * 100) / 100;
}

/** 万分之显示转手续费率（如 2.5 → 0.00025） */
export function displayToFeeRate(display: number): number {
  return display / 10000;
}

/** 印花税率转千分之显示（如 0.001 → 1） */
export function stampDutyToDisplay(rate: number): number {
  return Math.round(rate * 1000 * 100) / 100;
}

/** 千分之显示转印花税率（如 1 → 0.001） */
export function displayToStampDuty(display: number): number {
  return display / 1000;
}

/** 滑点率转万分之显示（如 0.0001 → 1） */
export function slippageToDisplay(rate: number): number {
  return Math.round(rate * 10000 * 100) / 100;
}

/** 万分之显示转滑点率（如 1 → 0.0001） */
export function displayToSlippage(display: number): number {
  return display / 10000;
}

/** 百分比转小数（如 3 → 0.03） */
export function pctToDecimal(pct: number): number {
  return pct / 100;
}

/** 小数转百分比显示（如 0.03 → 3） */
export function decimalToPct(decimal: number): number {
  return Math.round(decimal * 100 * 100) / 100;
}
