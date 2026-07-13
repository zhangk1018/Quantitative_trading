// backtestTypes.ts — 回测分析模块全部类型定义

import type { KlineBar } from '../../lib/indicators/indicators';

// ==================== 条件定义 ====================

export type ConditionFieldKey =
  | 'macd_golden_cross'
  | 'macd_death_cross'
  | 'rsi_oversold'
  | 'rsi_overbought'
  | 'volume_breakout'
  | 'volume_shrink'
  | 'consecutive_up'
  | 'consecutive_down'
  | 'ma_golden_cross'
  | 'ma_death_cross';

export interface BacktestCondition {
  fieldKey: ConditionFieldKey;
  label: string;
  params?: Record<string, number>;
}

// ==================== 指标参数配置 ====================

export interface IndicatorParams {
  ma5: number;
  ma10: number;
  ma20: number;
  ma60: number;
  bollPeriod: number;
  bollStd: number;
  macdFast: number;
  macdSlow: number;
  macdSignal: number;
  rsiPeriod: number;
  kdjK: number;
  kdjD: number;
  kdjJ: number;
}

export const DEFAULT_INDICATOR_PARAMS: IndicatorParams = {
  ma5: 5,
  ma10: 10,
  ma20: 20,
  ma60: 60,
  bollPeriod: 20,
  bollStd: 2,
  macdFast: 12,
  macdSlow: 26,
  macdSignal: 9,
  rsiPeriod: 6,
  kdjK: 9,
  kdjD: 3,
  kdjJ: 3,
};

// ==================== 回测配置 ====================

export interface BacktestConfig {
  stockCode: string;
  stockName: string;
  startDate: string;
  endDate: string;
  capital: number;
  buyConditions: BacktestCondition[];
  indicatorParams: IndicatorParams;
  executionPrice: 'next_open' | 'next_close';
  signalConfirmBars: number;
  maxDeferDays: number;
  feeRate: number;
  slippage: number;
  riskFreeRate: number;
}

export const DEFAULT_BACKTEST_CONFIG: Partial<BacktestConfig> = {
  capital: 100000,
  executionPrice: 'next_open',
  signalConfirmBars: 2,
  maxDeferDays: 3,
  feeRate: 0,
  slippage: 0,
  riskFreeRate: 0.03,
};

// ==================== 回测引擎输入/输出 ====================

export interface BacktestInput {
  bars: KlineBar[];
  buyConditions: BacktestCondition[];
  config: {
    stockCode: string;                // 新增：用于涨跌停判断
    capital: number;
    feeRate: number;
    slippage: number;
    riskFreeRate: number;
    executionPrice: 'next_open' | 'next_close';
    signalConfirmBars: number;
    maxDeferDays: number;
    indicatorParams: IndicatorParams;
  };
}

export type TradeDirection = 'buy' | 'sell' | 'close';

export interface Trade {
  id: number;
  direction: TradeDirection;
  entryTime: string;
  exitTime: string;
  entryPrice: number;
  exitPrice: number;
  shares: number;
  profit: number;
  profitPct: number;
  holdDays: number;
  isForcedClose: boolean;
  entryReason: string;
  exitReason: string;
}

export interface EquityPoint {
  time: string;
  equity: number;
  drawdown: number;
}

export interface BacktestSummary {
  totalReturn: number;
  annualizedReturn: number;
  winRate: number;
  profitLossRatio: number;
  maxDrawdown: number;
  maxConsecutiveLoss: number;
  avgHoldDays: number;
  sharpeRatio: number;
  totalTrades: number;
  forcedCloseCount: number;
  benchmarkReturn: number;
  tradingDays: number;
  warmupDays: number;
}

export interface BacktestOutput {
  trades: Trade[];
  equityCurve: EquityPoint[];
  summary: BacktestSummary;
  warnings: string[];
}

// ==================== 回测生命周期状态 ====================

export type BacktestPhase =
  | 'idle'
  | 'fetching'
  | 'calculating'
  | 'finished'
  | 'error'
  | 'cancelled';

export type CalcStage = 'fetching' | 'indicators' | 'signals' | 'simulating' | 'done';

export interface ProgressInfo {
  stage: CalcStage;
  percent: number;
  message: string;
}

// ==================== 存储结果 ====================

export interface StoredBacktestResult {
  id: string;
  createdAt: string;
  config: BacktestConfig;
  output: BacktestOutput;
}

// ==================== 条件映射表 ====================

export const REVERSE_CONDITION_MAP: Record<ConditionFieldKey, ConditionFieldKey> = {
  macd_golden_cross: 'macd_death_cross',
  macd_death_cross: 'macd_golden_cross',
  rsi_oversold: 'rsi_overbought',
  rsi_overbought: 'rsi_oversold',
  volume_breakout: 'volume_shrink',
  volume_shrink: 'volume_breakout',
  consecutive_up: 'consecutive_down',
  consecutive_down: 'consecutive_up',
  ma_golden_cross: 'ma_death_cross',
  ma_death_cross: 'ma_golden_cross',
};

export const CONDITION_LABEL_MAP: Record<ConditionFieldKey, string> = {
  macd_golden_cross: 'MACD金叉',
  macd_death_cross: 'MACD死叉',
  rsi_oversold: 'RSI超卖',
  rsi_overbought: 'RSI超买',
  volume_breakout: '放量突破',
  volume_shrink: '缩量跌破',
  consecutive_up: '连续上涨',
  consecutive_down: '连续下跌',
  ma_golden_cross: 'MA金叉',
  ma_death_cross: 'MA死叉',
};

export const BUY_CONDITION_KEYS: ConditionFieldKey[] = [
  'macd_golden_cross',
  'rsi_oversold',
  'volume_breakout',
  'consecutive_up',
  'ma_golden_cross',
];

/** 根据股票代码前缀获取涨跌停比例 */
export function getLimitPctByCode(stockCode: string): number {
  const code = stockCode.trim();
  if (code.startsWith('300') || code.startsWith('688')) {
    return 0.20; // 创业板、科创板 20%
  }
  if (code.startsWith('8') || code.startsWith('43')) {
    return 0.30; // 北交所 30%（简化）
  }
  // ST 股票需额外判断，此处简化，可通过扩展参数覆盖
  return 0.10; // 主板默认 10%
}