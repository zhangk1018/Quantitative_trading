export const OHLCV_TIME = 0;
export const OHLCV_OPEN = 1;
export const OHLCV_HIGH = 2;
export const OHLCV_LOW = 3;
export const OHLCV_CLOSE = 4;
export const OHLCV_VOLUME = 5;

export interface KLineItem {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface SignalItem {
  time: string;
  position: 'aboveBar' | 'belowBar';
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
  color: string;
  text?: string;
}

export type OHLCVArray = [
  time: number,
  open: number,
  high: number,
  low: number,
  close: number,
  volume: number
];

export interface StockSnapshot {
  code: string;
  name: string;
  listed_board: string;
  industry: string;
  trade_date: string;
  close: number;
  change_pct: number;
  market_cap: number;
  turnover_rate: number;
  pe_ttm: number;
  pb: number;
  indicators: StandardIndicators;
  ohlcv: OHLCVArray[];
}

export interface StandardIndicators {
  ma5: number;
  ma10: number;
  ma20: number;
  ma60: number | null;
  rsi_6: number;
  rsi_12: number;
  rsi_24: number;
  macd_dif: number;
  macd_dea: number;
  macd: number;
  boll_upper: number;
  boll_mid: number;
  boll_lower: number;
  is_macd_golden_cross: 0 | 1;
  is_macd_dead_cross: 0 | 1;
}

export type PatternType =
  | 'hammer'
  | 'morning_star'
  | 'evening_star'
  | 'bullish_engulfing'
  | 'bearish_engulfing';

export interface PatternDetectionResult {
  hits: PatternType[];
  hitDays: Record<PatternType, number[]>;
}