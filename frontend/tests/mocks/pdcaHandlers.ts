/**
 * PDCA 交易自律系统 — MSW mock handlers
 *
 * 覆盖：
 * - 交易记录 CRUD（fetchRecords / createRecord / updateRecord / deleteRecord）
 * - 交易日记 API（fetchDiaries / createDiary / updateDiary）
 * - 资金快照（saveSnapshot / fetchCapitalCurve）
 * - 系统配置（fetchConfig / updateConfig）
 * - 券商导入（fetchBrokerAdapters / parseImportExcel / confirmImport）
 * - 股票搜索（searchStocks）
 * - PDCA 周期（fetchCycles）
 * - 导出 / 备份（exportRecords / backupDatabase）
 * - 错误场景（400/500）
 */

import { http, HttpResponse } from 'msw';
import type { ApiResponse, ListData, PaginatedData, TradingRecord, TradingRecordFormData, BrokerAdapter, ImportParseResult, SystemConfigItem, CapitalCurvePoint, TradingDiary } from '@/features/pdca/types';

// ── Mock 初始数据 ──

const INITIAL_RECORDS: TradingRecord[] = [
  {
    id: 1, account_id: 1, pdca_cycle_id: 1, trading_plan_id: null,
    code: '600036', security_name: '招商银行', instrument_type: 'stock',
    long_short: 'long', order_type: 'limit',
    entry_date: '2026-08-01', exit_date: '2026-08-05',
    entry_price: 35.20, exit_price: 36.50, quantity: 1000,
    commission_entry: 5.0, commission_exit: 5.0, slip_point: 0.01,
    channel_height: null, gross_profit: 1300.00,
    entry_score: 85, exit_score: 80, trade_score: 82.5,
    trade_grade: 'A', trigger_source: 'system_plan',
    actual_stop_loss: null, exit_reason: 'take_profit',
    settlement_currency: 'CNY',
    created_at: '2026-08-01T09:30:00Z', updated_at: '2026-08-05T15:00:00Z',
  },
  {
    id: 2, account_id: 1, pdca_cycle_id: 1, trading_plan_id: null,
    code: '000001', security_name: '平安银行', instrument_type: 'stock',
    long_short: 'long', order_type: 'market',
    entry_date: '2026-08-03', exit_date: '2026-08-06',
    entry_price: 11.06, exit_price: 10.80, quantity: 2000,
    commission_entry: 5.0, commission_exit: 5.0, slip_point: 0.02,
    channel_height: null, gross_profit: -520.00,
    entry_score: 70, exit_score: 60, trade_score: 65.0,
    trade_grade: 'B', trigger_source: 'scanner',
    actual_stop_loss: 10.50, exit_reason: 'stop_loss',
    settlement_currency: 'CNY',
    created_at: '2026-08-03T10:00:00Z', updated_at: '2026-08-06T14:30:00Z',
  },
];

// 可变副本，允许测试在 beforeEach 中重置
let mockRecords: TradingRecord[] = [...INITIAL_RECORDS];
let nextRecordId = 3;

/** 在每个测试用例前重置 mock 数据，避免状态污染 */
export function resetMockData(): void {
  mockRecords = INITIAL_RECORDS.map((r) => ({ ...r }));
  nextRecordId = 3;
}

// ── Handlers ──

export const pdcaHandlers = [
  // ── 交易记录 ──

  http.get('/api/pdca/records', ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') ?? '1');
    const limit = Number(url.searchParams.get('limit') ?? '20');
    const code = url.searchParams.get('code');
    const entryDateFrom = url.searchParams.get('entry_date_from');
    const entryDateTo = url.searchParams.get('entry_date_to');

    let filtered = [...mockRecords];
    if (code) {
      filtered = filtered.filter((r) => r.code.includes(code));
    }
    if (entryDateFrom) {
      filtered = filtered.filter((r) => r.entry_date >= entryDateFrom);
    }
    if (entryDateTo) {
      filtered = filtered.filter((r) => r.entry_date <= entryDateTo);
    }

    const total = filtered.length;
    const start = (page - 1) * limit;
    const items = filtered.slice(start, start + limit);

    const response: ApiResponse<PaginatedData<TradingRecord>> = {
      code: 200,
      message: 'ok',
      data: { items, total, page, page_size: limit },
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/pdca/records', async ({ request }) => {
    const body = (await request.json()) as TradingRecordFormData;
    // 模拟参数校验：缺少必填字段返回 400
    if (!body.code || !body.entry_date || !body.entry_price) {
      return HttpResponse.json(
        { code: 400, message: '缺少必填字段', data: null },
        { status: 400 },
      );
    }
    const newRecord: TradingRecord = {
      id: nextRecordId++,
      account_id: 1,
      pdca_cycle_id: body.pdca_cycle_id ?? 1,
      trading_plan_id: null,
      code: body.code,
      security_name: body.security_name,
      instrument_type: body.instrument_type,
      long_short: body.long_short,
      order_type: body.order_type,
      entry_date: body.entry_date,
      exit_date: body.exit_date ?? null,
      entry_price: body.entry_price,
      exit_price: body.exit_price ?? null,
      quantity: body.quantity,
      commission_entry: body.commission_entry,
      commission_exit: body.commission_exit,
      slip_point: body.slip_point,
      channel_height: body.channel_height ?? null,
      gross_profit: body.gross_profit ?? null,
      entry_score: body.entry_score ?? null,
      exit_score: body.exit_score ?? null,
      trade_score: body.trade_score ?? null,
      trade_grade: body.trade_grade ?? null,
      trigger_source: body.trigger_source ?? null,
      actual_stop_loss: body.actual_stop_loss ?? null,
      exit_reason: body.exit_reason ?? null,
      settlement_currency: 'CNY',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    mockRecords.push(newRecord);
    const response: ApiResponse<TradingRecord> = { code: 200, message: 'ok', data: newRecord };
    return HttpResponse.json(response);
  }),

  http.put('/api/pdca/records/:id', async ({ request, params }) => {
    const id = Number(params.id);
    const body = (await request.json()) as Partial<TradingRecordFormData>;
    const idx = mockRecords.findIndex((r) => r.id === id);
    if (idx === -1) {
      return HttpResponse.json({ code: 404, message: '记录不存在', data: null }, { status: 404 });
    }
    mockRecords[idx] = { ...mockRecords[idx], ...body, updated_at: new Date().toISOString() };
    const response: ApiResponse<TradingRecord> = { code: 200, message: 'ok', data: mockRecords[idx] };
    return HttpResponse.json(response);
  }),

  http.delete('/api/pdca/records/:id', ({ params }) => {
    const id = Number(params.id);
    const idx = mockRecords.findIndex((r) => r.id === id);
    if (idx === -1) {
      return HttpResponse.json({ code: 404, message: '记录不存在', data: null }, { status: 404 });
    }
    mockRecords.splice(idx, 1);
    const response: ApiResponse<null> = { code: 200, message: 'ok', data: null };
    return HttpResponse.json(response);
  }),

  // ── 资金快照 ──

  http.get('/api/pdca/snapshots/curve', () => {
    const response: ApiResponse<ListData<CapitalCurvePoint>> = {
      code: 200,
      message: 'ok',
      data: {
        items: [
          { date: '2026-08-01', total_asset: 1000000, adjusted_nav: 1000000, deposit: 0, withdrawal: 0, realized_pnl: 0 },
          { date: '2026-08-05', total_asset: 1013000, adjusted_nav: 1013000, deposit: 0, withdrawal: 0, realized_pnl: 1300 },
        ],
      },
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/pdca/snapshots', () => {
    const response: ApiResponse<{ id: number }> = {
      code: 200, message: 'ok', data: { id: 10 },
    };
    return HttpResponse.json(response);
  }),

  // ── 交易日记 ──

  http.get('/api/pdca/diaries', () => {
    const response: ApiResponse<PaginatedData<TradingDiary>> = {
      code: 200, message: 'ok', data: { items: [], total: 0, page: 1, page_size: 50 },
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/pdca/diaries', () => {
    const response: ApiResponse<{ id: number }> = {
      code: 200, message: 'ok', data: { id: 1 },
    };
    return HttpResponse.json(response);
  }),

  http.put('/api/pdca/diaries/:id', () => {
    const response: ApiResponse<{ id: number }> = {
      code: 200, message: 'ok', data: { id: 1 },
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/pdca/diaries/:id/upload', () => {
    const response: ApiResponse<{ file_path: string }> = {
      code: 200, message: 'ok', data: { file_path: '/uploads/test.png' },
    };
    return HttpResponse.json(response);
  }),

  // ── 系统配置 ──

  http.get('/api/pdca/config', () => {
    const response: ApiResponse<ListData<SystemConfigItem>> = {
      code: 200, message: 'ok',
      data: {
        items: [
          {
            id: 1, config_key: 'risk_per_trade', config_value: '2', numeric_value: 2, bool_value: null,
            description: '单笔风险上限', version: '1.0', modified_at: '2026-08-01T00:00:00Z',
            modified_by: null, modify_reason: '',
          },
          {
            id: 2, config_key: 'risk_per_month', config_value: '6', numeric_value: 6, bool_value: null,
            description: '月度总风险上限', version: '1.0', modified_at: '2026-08-01T00:00:00Z',
            modified_by: null, modify_reason: '',
          },
        ],
      },
    };
    return HttpResponse.json(response);
  }),

  http.put('/api/pdca/config', () => {
    const response: ApiResponse<SystemConfigItem> = {
      code: 200, message: 'ok', data: {
        id: 1, config_key: 'risk_per_trade', config_value: '3', numeric_value: 3, bool_value: null,
        description: '单笔风险上限', version: '1.0', modified_at: '2026-08-01T00:00:00Z',
        modified_by: null, modify_reason: '测试调整',
      },
    };
    return HttpResponse.json(response);
  }),

  // ── 券商导入 ──

  http.get('/api/pdca/import/brokers', () => {
    const response: ApiResponse<ListData<BrokerAdapter>> = {
      code: 200, message: 'ok',
      data: { items: [
        { id: 1, broker_name: 'ht', display_name: '华泰证券', is_active: true, column_mapping: { code: '证券代码' }, date_format: 'YYYY-MM-DD', skip_rows: 1 },
        { id: 2, broker_name: 'citics', display_name: '中信证券', is_active: true, column_mapping: { code: '股票代码' }, date_format: 'YYYY-MM-DD', skip_rows: 2 },
      ] },
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/pdca/import/parse', () => {
    const response: ApiResponse<ImportParseResult> = {
      code: 200, message: 'ok',
      data: {
        broker_name: 'ht', total_rows: 6, valid_rows: 5, error_rows: 1,
        records: [
          { code: '600036', security_name: '招商银行', instrument_type: 'stock', long_short: 'long', order_type: 'limit', entry_date: '2026-08-01', entry_price: 35.20, quantity: 1000, commission_entry: 0, commission_exit: 0, slip_point: 0, exit_date: '2026-08-05', exit_price: 36.50 },
          { code: '000001', security_name: '平安银行', instrument_type: 'stock', long_short: 'long', order_type: 'market', entry_date: '2026-08-03', entry_price: 11.06, quantity: 2000, commission_entry: 0, commission_exit: 0, slip_point: 0, exit_date: '2026-08-06', exit_price: 10.80 },
        ],
        errors: [{ row: 3, message: '无效的股票代码' }],
      },
    };
    return HttpResponse.json(response);
  }),

  http.post('/api/pdca/import/confirm', () => {
    const response: ApiResponse<{ imported: number }> = {
      code: 200, message: 'ok', data: { imported: 5 },
    };
    return HttpResponse.json(response);
  }),

  // ── 股票搜索 ──

  http.get('/api/pdca/stocks/search', ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get('q') ?? '';
    const response: ApiResponse<{ code: string; name: string; listed_board: string | null }[]> = {
      code: 200, message: 'ok',
      data: q
        ? [{ code: '600036', name: '招商银行', listed_board: '上海主板' }]
        : [{ code: '600036', name: '招商银行', listed_board: '上海主板' }, { code: '000001', name: '平安银行', listed_board: '深圳主板' }],
    };
    return HttpResponse.json(response);
  }),

  // ── PDCA 周期 ──

  http.get('/api/pdca/cycles', ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get('status');
    const cycles = status === 'DO'
      ? [{ id: 1, account_id: 1, prev_cycle_id: null, cycle_type: 'week' as const, cycle_name: 'W24-33', status: 'DO' as const, start_date: '2026-08-01', end_date: '2026-08-07', goal_text: null, created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z' }]
      : [];
    return HttpResponse.json({ code: 200, message: 'ok', data: { items: cycles } });
  }),

  // ── 导出 / 备份 ──

  http.get('/api/pdca/export', () => {
    return HttpResponse.arrayBuffer(new ArrayBuffer(0), {
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    });
  }),

  http.get('/api/pdca/backup', () => {
    return HttpResponse.text('-- SQL backup content --', {
      headers: { 'Content-Type': 'text/plain' },
    });
  }),

  // ── 错误场景 ──

  /** 模拟服务器 500 错误 */
  http.get('/api/pdca/error-500', () => {
    return HttpResponse.json(
      { code: 500, message: '服务器内部错误', data: null },
      { status: 500 },
    );
  }),

  /** 模拟参数校验 400 错误 */
  http.get('/api/pdca/error-400', () => {
    return HttpResponse.json(
      { code: 400, message: '参数校验失败', data: null },
      { status: 400 },
    );
  }),
];