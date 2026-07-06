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

  // ==================== K 线 ====================
  http.get('/api/kline/:code', ({ request, params }) => {
    const url = new URL(request.url);
    const code = params.code as string;
    const limit = Number(url.searchParams.get('limit') ?? '500');

    // 生成 mock K 线数据
    const baseDate = new Date('2026-07-01');
    const rawItems = Array.from({ length: Math.min(limit, 10) }, (_, i) => {
      const d = new Date(baseDate);
      d.setDate(d.getDate() + i);
      const dateStr = d.toISOString().slice(0, 10);
      // 仅交易日（跳过周末）
      if (d.getDay() === 0 || d.getDay() === 6) return null;
      const open = 35 + i * 0.1;
      const close = open + (i % 3 === 0 ? -0.5 : 0.3);
      return {
        trade_date: dateStr,
        open: String(open),
        high: String(Math.max(open, close) + 0.5),
        low: String(Math.min(open, close) - 0.5),
        close: String(close),
        volume: '1000000',
        amount: '35000000',
        pe_ttm: '5.1',
        turnover_rate: '0.85',
      };
    }).filter(Boolean);

    // 带有 pattern_markers 的完整响应（直接返回 KLineResponse，非 ApiResponse 信封）
    const response = {
      stock_code: code,
      data: rawItems,
      count: rawItems.length,
      adj_method: 'forward',
      pattern_markers: [
        { date: '2026-07-03', patterns: ['hammer'] },
        { date: '2026-07-06', patterns: ['morning_star', 'bullish_engulfing'] },
      ],
    };

    return HttpResponse.json(response);
  }),
];
