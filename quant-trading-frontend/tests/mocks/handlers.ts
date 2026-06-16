import { http, HttpResponse } from 'msw';
import type { StockItem, ApiEnvelope } from './types';

// 测试用 mock 数据
const mockStocks: StockItem[] = [
  {
    stock_code: '600036',
    stock_name: '招商银行',
    close: 35.20,
    change_pct: 1.25,
    turnover_rate: 0.85,
    pe: 5.4,
    pe_ttm: 5.1,
    pb: 0.92,
    market_cap: 895600000000,
    amount: 1234000000,
    listed_board: '上海主板',
  },
  {
    stock_code: '000001',
    stock_name: '平安银行',
    close: 11.06,
    change_pct: -0.85,
    turnover_rate: 0.62,
    pe: 4.8,
    pe_ttm: 4.5,
    pb: 0.55,
    market_cap: 215000000000,
    amount: 567000000,
    listed_board: '深圳主板',
  },
  {
    stock_code: '300750',
    stock_name: '宁德时代',
    close: 235.80,
    change_pct: 3.45,
    turnover_rate: 1.85,
    pe: 22.5,
    pe_ttm: 21.0,
    pb: 4.2,
    market_cap: 1038000000000,
    amount: 8500000000,
    listed_board: '创业板',
  },
];

// 拦截后端 /api/stocks/ 请求
export const stocksHandlers = [
  http.get('/api/stocks/', ({ request }) => {
    const url = new URL(request.url);
    const offset = Number(url.searchParams.get('offset') ?? '0');
    const limit = Number(url.searchParams.get('limit') ?? '20');
    const sortBy = url.searchParams.get('sort_by') ?? 'change_pct';
    const sortAsc = url.searchParams.get('sort_asc') === 'true';

    // 模拟排序
    const sorted = [...mockStocks].sort((a, b) => {
      const va = a[sortBy as keyof StockItem] as number;
      const vb = b[sortBy as keyof StockItem] as number;
      return sortAsc ? va - vb : vb - va;
    });

    const items = sorted.slice(offset, offset + limit);

    const response: ApiEnvelope<{ items: StockItem[]; total: number }> = {
      code: 200,
      message: 'ok',
      data: {
        items,
        total: mockStocks.length,
      },
    };

    return HttpResponse.json(response);
  }),

  // 模拟错误场景
  http.get('/api/stocks/error', () => {
    return HttpResponse.json(
      { code: 500, message: '服务器内部错误', data: null },
      { status: 500 }
    );
  }),
];
