import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../mocks/server';
import { App as AntdApp } from 'antd';
import StockPickerView from '@/features/stock-picker/StockPickerView';
import { ScreenerProvider } from '@/features/stock-picker/context/ScreenerContext';
import { SettingsProvider } from '@/shared/contexts/SettingsContext';

// ================================================================
// StockPickerView 集成测试（行情指标 + runScreening）
// 共 13 个测试：A10 参数映射 (7) + A10b 技术指标 (2) + A11 表格渲染 (3) + A12 重置 (1)
//
// 修复关键点：
// 1. vi.mock('@/features/stock-detail/api') 替代 vi.spyOn：vi.spyOn 只作用于
//    测试文件的 namespace import，无法影响 useScreenerData 的 named import
// 2. vi.mock('@tanstack/react-virtual')：jsdom 无真实布局，getVirtualItems() 返回
//    空数组，mock 为返回所有 items 绕过 DOM 尺寸依赖
// ================================================================

// 模拟 fetchStocks，默认走真实实现（让 MSW 拦截 A10 测试），
// A11 测试中通过 mockImplementation 覆盖返回值
const { fetchStocksRef } = vi.hoisted(() => ({
  fetchStocksRef: { current: null as ((...args: any[]) => any) | null },
}));

vi.mock('@/features/stock-detail/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/stock-detail/api')>();
  return {
    ...actual,
    fetchStocks: vi.fn((...args: any[]) => {
      if (fetchStocksRef.current) {
        return fetchStocksRef.current(...args);
      }
      return (actual.fetchStocks as Function)(...args);
    }),
  };
});

// 模拟 useWatchlist，避免 WatchlistProvider 的异步初始化在测试环境挂起
vi.mock('@/features/watchlist/store', () => {
  const mockState = { customGroups: [], stocks: {}, loading: false, migrated: true };
  return {
    useWatchlist: () => ({
      state: mockState,
      allGroups: [],
      addOne: vi.fn(),
      addMany: vi.fn(() => ({ added: 0, skipped: 0, failed: 0, errors: [] })),
      removeOne: vi.fn(),
      createGroup: vi.fn(() => true),
      deleteGroup: vi.fn(),
      refresh: vi.fn(),
    }),
    WatchlistProvider: ({ children }: { children: React.ReactNode }) => children,
  };
});

// 模拟 @tanstack/react-virtual：jsdom 无真实布局，虚拟滚动 getVirtualItems 永远返回空数组。
// 直接 mock 为返回所有 items，绕过 DOM 尺寸依赖。
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: vi.fn((options: { count: number }) => ({
    getVirtualItems: () => Array.from({ length: options.count }, (_, i) => ({
      index: i,
      size: 48,
      start: i * 48,
      key: i,
      measureElement: vi.fn(),
    })),
    getTotalSize: () => options.count * 48,
    scrollToIndex: vi.fn(),
    measure: vi.fn(),
  })),
}));

// 覆盖默认 5000ms timeout：coverage 模式下 MSW + jsdom 比正常慢，5s 不够
vi.setConfig({ testTimeout: 15000 });

// 捕获最后一次 /api/stocks/ 请求的 query 参数
let lastRequestUrl: string | null = null;
let requestLog: Array<{ url: string; at: number }> = [];

beforeEach(() => {
  lastRequestUrl = null;
  requestLog = [];

  // 拦截 /api/stocks/，记录 URL 并返回 mock 数据
  server.use(
    http.get('/api/stocks/', ({ request }) => {
      lastRequestUrl = request.url;
      requestLog.push({ url: request.url, at: Date.now() });

      const url = new URL(request.url);
      const offset = Number(url.searchParams.get('offset') ?? '0');
      const limit = Number(url.searchParams.get('limit') ?? '20');
      const sortBy = url.searchParams.get('sort_by') ?? 'change_pct';
      const sortAsc = url.searchParams.get('sort_asc') === 'true';

      const all = [
        {
          stock_code: '600036',
          stock_name: '招商银行',
          close: 35.2,
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
      ];

      const sorted = [...all].sort((a, b) => {
        const va = a[sortBy as keyof typeof a] as number;
        const vb = b[sortBy as keyof typeof b] as number;
        return sortAsc ? va - vb : vb - va;
      });
      const items = sorted.slice(offset, offset + limit);

      return HttpResponse.json({
        code: 200,
        message: 'ok',
        data: { items, total: all.length },
      });
    }),
  );
});

afterEach(() => {
  server.resetHandlers();
});

// 包装完整 providers
// K 2026-06-17 变更：ConditionBuilder 使用 useNavigate（跳转 /config），
// 需要 MemoryRouter 提供 Router 上下文
// StockPickerView 使用 antd App.useApp()，需要 AntdApp 包装
function renderView() {
  return render(
    <MemoryRouter>
      <AntdApp>
        <SettingsProvider>
          <ScreenerProvider>
            <StockPickerView />
          </ScreenerProvider>
        </SettingsProvider>
      </AntdApp>
    </MemoryRouter>
  );
}

// 工具：展开行情指标面板
async function expandIndicatorPanel(user: ReturnType<typeof userEvent.setup>) {
  const header = screen.getByText('行情指标').closest('.ant-collapse-header');
  if (header) {
    await user.click(header);
  }
}

describe('StockPickerView 集成测试（行情指标 + runScreening）', () => {
  describe('A10: runScreening 参数映射', () => {
    it('未传任何筛选条件时请求参数不带 listed_board / *_min / *_max', async () => {
      const user = userEvent.setup();
      renderView();

      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      expect(url.searchParams.get('listed_board')).toBeNull();
      // *_min / *_max 也不应有
      const allKeys = Array.from(url.searchParams.keys());
      expect(allKeys.some((k) => k.endsWith('_min'))).toBe(false);
      expect(allKeys.some((k) => k.endsWith('_max'))).toBe(false);
    });

    it('单选一个行情指标 + 设置范围后，URL 包含 *_min 和 *_max', async () => {
      const user = userEvent.setup();
      renderView();
      await expandIndicatorPanel(user);

      // 点击"市值"指标
      await user.click(screen.getByTestId('indicator-btn-market_cap'));
      // 设置 min 和 max（InputNumber 的 data-testid 直接加在 input 上）
      const minInput = screen.getByTestId('indicator-min-market_cap');
      const maxInput = screen.getByTestId('indicator-max-market_cap');
      fireEvent.change(minInput, { target: { value: '100' } });
      fireEvent.change(maxInput, { target: { value: '500' } });

      // 点击"开始选股"
      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      // market_cap 显示单位"亿元"，前端 ×10000 转换为"万元"传给后端
      expect(url.searchParams.get('market_cap_min')).toBe('1000000');
      expect(url.searchParams.get('market_cap_max')).toBe('5000000');
    });

    it('范围只设置 min 时，max 参数不传', async () => {
      const user = userEvent.setup();
      renderView();
      await expandIndicatorPanel(user);
      await user.click(screen.getByTestId('indicator-btn-volume'));
      const minInput = screen.getByTestId('indicator-min-volume');
      fireEvent.change(minInput, { target: { value: '1000' } });

      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      expect(url.searchParams.get('volume_min')).toBe('1000');
      expect(url.searchParams.get('volume_max')).toBeNull();
    });

    it('空字符串 range 不应被序列化到 URL', async () => {
      const user = userEvent.setup();
      renderView();
      await expandIndicatorPanel(user);
      // 选中指标但不改任何值
      await user.click(screen.getByTestId('indicator-btn-turnover'));

      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      expect(url.searchParams.get('turnover_min')).toBeNull();
      expect(url.searchParams.get('turnover_max')).toBeNull();
    });

    it('多个行情指标 range 全部正确序列化', async () => {
      const user = userEvent.setup();
      renderView();
      await expandIndicatorPanel(user);
      await user.click(screen.getByTestId('indicator-btn-market_cap'));
      await user.click(screen.getByTestId('indicator-btn-volume'));

      fireEvent.change(screen.getByTestId('indicator-min-market_cap'), {
        target: { value: '50' },
      });
      fireEvent.change(screen.getByTestId('indicator-max-volume'), {
        target: { value: '9999' },
      });

      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      // market_cap 显示"亿元"，×10000 转"万元"；volume 不做单位转换（显示"手"）
      expect(url.searchParams.get('market_cap_min')).toBe('500000');
      expect(url.searchParams.get('volume_max')).toBe('9999');
    });
  });

  describe('A10b: 技术指标 URL 序列化', () => {
    // 工具：展开技术指标面板（用 data-testid 定位 header）
    async function expandTechnicalPanel() {
      const user = userEvent.setup();
      await user.click(screen.getByTestId('technical-filter-header'));
      return user;
    }

    it('选中 1 个技术指标（MA）后，URL 包含 tech_ma=<option>', { timeout: 15000 }, async () => {
      renderView();
      const user = await expandTechnicalPanel();

      // 点击 MA 按钮打开弹窗
      await user.click(screen.getByTestId('technical-btn-ma'));
      await screen.findByTestId('technical-modal-ma');
      // 选"多头排列"
      await user.click(screen.getByTestId('technical-modal-ma-option-long_align'));
      // 确定
      await user.click(screen.getByTestId('technical-modal-ma-confirm'));
      await waitFor(() =>
        expect(screen.queryByTestId('technical-modal-ma')).not.toBeInTheDocument()
      );

      // 点击"开始选股"
      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      expect(url.searchParams.get('tech_ma')).toBe('long_align');
    });

    it('选中多个技术指标（MA + RSI + BOLL）后，URL 包含 tech_*=*', async () => {
      renderView();
      const user = await expandTechnicalPanel();

      // MA
      await user.click(screen.getByTestId('technical-btn-ma'));
      await screen.findByTestId('technical-modal-ma');
      await user.click(screen.getByTestId('technical-modal-ma-option-long_align'));
      await user.click(screen.getByTestId('technical-modal-ma-confirm'));
      await waitFor(() =>
        expect(screen.queryByTestId('technical-modal-ma')).not.toBeInTheDocument()
      );

      // RSI
      await user.click(screen.getByTestId('technical-btn-rsi'));
      await screen.findByTestId('technical-modal-rsi');
      await user.click(screen.getByTestId('technical-modal-rsi-option-low_golden_cross'));
      await user.click(screen.getByTestId('technical-modal-rsi-confirm'));
      await waitFor(() =>
        expect(screen.queryByTestId('technical-modal-rsi')).not.toBeInTheDocument()
      );

      // BOLL
      await user.click(screen.getByTestId('technical-btn-boll'));
      await screen.findByTestId('technical-modal-boll');
      await user.click(screen.getByTestId('technical-modal-boll-option-break_upper'));
      await user.click(screen.getByTestId('technical-modal-boll-confirm'));
      await waitFor(() =>
        expect(screen.queryByTestId('technical-modal-boll')).not.toBeInTheDocument()
      );

      // 点击"开始选股"
      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      expect(url.searchParams.get('tech_ma')).toBe('long_align');
      expect(url.searchParams.get('tech_rsi')).toBe('low_golden_cross');
      expect(url.searchParams.get('tech_boll')).toBe('break_upper');
      // MACD 未选
      expect(url.searchParams.get('tech_macd')).toBeNull();
    });

    it('未选任何技术指标时，URL 不包含 tech_*', { timeout: 15000 }, async () => {
      const user = userEvent.setup();
      renderView();
      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => expect(lastRequestUrl).not.toBeNull());
      const url = new URL(lastRequestUrl!);
      const allKeys = Array.from(url.searchParams.keys());
      expect(allKeys.some((k) => k.startsWith('tech_'))).toBe(false);
    });
  });

  describe('A11: loading → 成功 → 表格渲染', () => {
    const mockItems = [
      { stock_code: '000001', stock_name: '平安银行', close: 12.5, change_pct: 2.5, market_cap: 2.5e11, pe_ttm: 6.5, pb: 0.8, turnover_rate: 3.2, trade_date: '2026-07-11', amount: 1e9, pe: 6.5, listed_board: '主板' },
      { stock_code: '600036', stock_name: '招商银行', close: 42.0, change_pct: -1.2, market_cap: 8.956e11, pe_ttm: 5.8, pb: 0.9, turnover_rate: 1.5, trade_date: '2026-07-11', amount: 2e9, pe: 5.8, listed_board: '主板' },
    ];

    beforeEach(() => {
      fetchStocksRef.current = () => Promise.resolve({ items: mockItems, total: 2 });
    });

    afterEach(() => {
      fetchStocksRef.current = null;
    });

    it('点击"开始选股"后表格渲染 mock 数据', async () => {
      const user = userEvent.setup();
      renderView();

      await user.click(screen.getByTestId('start-screener'));

      // 等待 loading 状态结束 → 数据渲染
      await waitFor(() => {
        expect(screen.queryByText('正在加载数据...')).not.toBeInTheDocument();
      }, { timeout: 10000 });

      // 检查数据是否渲染
      await waitFor(() => {
        expect(screen.getByText('招商银行')).toBeInTheDocument();
      }, { timeout: 5000 });

      expect(screen.getByText('平安银行')).toBeInTheDocument();

      // 验证表头
      expect(screen.getByText('代码')).toBeInTheDocument();
      expect(screen.getByText('名称')).toBeInTheDocument();
      expect(screen.getByText('收盘价')).toBeInTheDocument();
    });

    it('顶部"共 N 只"显示 mock total', async () => {
      const user = userEvent.setup();
      renderView();
      await user.click(screen.getByTestId('start-screener'));

      // 等待表格行出现（说明 fetch 已完成）
      await screen.findByText('招商银行');

      // 然后断言"共 N 只"已经更新（顶部工具栏的 span）
      expect(await screen.findByText(/^共\s*2\s*只$/)).toBeInTheDocument();
    });

    it('成功加载后表格行显示格式化市值（亿）', async () => {
      const user = userEvent.setup();
      renderView();
      await user.click(screen.getByTestId('start-screener'));

      await waitFor(() => {
        expect(screen.getByText('招商银行')).toBeInTheDocument();
      });

      // 招商银行 market_cap=895600000000 → 89560.00亿
      const row = screen.getByText('招商银行').closest('tr')!;
      const cells = within(row).getAllByText(/亿$/);
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('A12: 重置清空非 context 状态', () => {
    const mockItems = [
      { stock_code: '000001', stock_name: '平安银行', close: 12.5, change_pct: 2.5, market_cap: 2.5e11, pe_ttm: 6.5, pb: 0.8, turnover_rate: 3.2, trade_date: '2026-07-11', amount: 1e9, pe: 6.5, listed_board: '主板' },
      { stock_code: '600036', stock_name: '招商银行', close: 42.0, change_pct: -1.2, market_cap: 8.956e11, pe_ttm: 5.8, pb: 0.9, turnover_rate: 1.5, trade_date: '2026-07-11', amount: 2e9, pe: 5.8, listed_board: '主板' },
    ];

    beforeEach(() => {
      fetchStocksRef.current = () => Promise.resolve({ items: mockItems, total: 2 });
    });

    afterEach(() => {
      fetchStocksRef.current = null;
    });

    it('点击重置后清空表格，回到"暂无数据"提示', async () => {
      const user = userEvent.setup();
      renderView();

      // 先加载数据
      await user.click(screen.getByTestId('start-screener'));
      await waitFor(() => expect(screen.getByText('招商银行')).toBeInTheDocument());

      // 点击重置
      await user.click(screen.getByTestId('reset-screener'));

      // 表格应消失，回到"暂无数据"提示
      await waitFor(() => {
        expect(screen.queryByText('招商银行')).not.toBeInTheDocument();
      });
      expect(screen.getByText(/暂无数据/)).toBeInTheDocument();
    });

    it('重置后 context 中行情指标选择也被清空', async () => {
      const user = userEvent.setup();
      renderView();
      await expandIndicatorPanel(user);
      await user.click(screen.getByTestId('indicator-btn-market_cap'));
      await user.click(screen.getByTestId('indicator-btn-volume'));

      // 验证已选中
      expect(screen.getByTestId('indicator-btn-market_cap')).toHaveAttribute(
        'data-selected',
        'true'
      );

      // 重置
      await user.click(screen.getByTestId('reset-screener'));

      // 验证状态清空（badge 应回到 0）
      await waitFor(() => {
        expect(screen.getByTestId('indicator-filter-badge')).toHaveTextContent('0');
      });
    });
  });
});
