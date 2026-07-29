// src/shared/types/stock.ts

export interface KLineItem {
  time: string; // Lightweight Charts 支持 'YYYY-MM-DD'
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SignalItem {
  time: string;
  position: 'aboveBar' | 'belowBar' | 'inBar';
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
  color: string;
  text: string;
}

export interface StockDetail {
  code: string;
  name: string;
  pe?: number;
  pb?: number;
  market_cap?: number;
  total_shares?: number;
  industry?: string;
}