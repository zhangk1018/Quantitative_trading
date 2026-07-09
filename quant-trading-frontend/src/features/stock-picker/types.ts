/** 选股器结果行数据类型 */
export interface StockItem {
  stock_code: string;
  stock_name: string;
  close: number | null;
  change_pct: number | null;
  turnover_rate: number | null;
  pe: number | null;
  pe_ttm?: number | null;
  pb: number | null;
  market_cap: number | null;
  amount: number | null;
  listed_board: string | null;
  patterns?: string[];
}

/** API 响应类型 */
export interface FetchStocksResponse {
  items: StockItem[];
  total: number;
}