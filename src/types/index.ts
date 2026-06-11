export interface KLineData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
  rsi?: number;
  macd?: number;
  dif?: number;
  dea?: number;
}

export interface StockInfo {
  code: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
}

export type TimePeriod = '1d' | '1w' | '1m';
