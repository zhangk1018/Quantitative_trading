/**
 * MSW 测试用类型定义
 * 与 frontend/src/types.ts 中 StockResponse 保持一致（仅保留测试需要字段）
 */

export interface StockItem {
  stock_code: string;
  stock_name: string;
  close: number;
  change_pct: number;
  turnover_rate: number;
  pe?: number;
  pe_ttm?: number;
  pb?: number;
  market_cap: number;
  amount: number;
  listed_board: string;
}

export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
}
