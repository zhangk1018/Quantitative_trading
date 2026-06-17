import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../mocks/server';
import StockPickerView from '@/features/stock-picker/StockPickerView';
import { ScreenerProvider, useScreener } from '@/features/stock-picker/context/ScreenerContext';
import { SettingsProvider } from '@/shared/contexts/SettingsContext';

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
    })
  );
});

afterEach(() => {
  server.resetHandlers();
});

// 包装完整 providers
// K 2026-06-17 变更：ConditionBuilder 使用 useNavigate（跳转 /config），
// 需要 MemoryRouter 提供 Router 上下文
function renderView() {
  return render(
    <MemoryRouter>
      <SettingsProvider>
        <ScreenerProvider>
          <StockPickerView />
        </ScreenerProvider>
      </SettingsProvider>
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
    it('点击"开始选股"后表格渲染 mock 数据', async () => {
      const user = userEvent.setup();
      renderView();

      await user.click(screen.getByTestId('start-screener'));

      // 等待数据加载完成，表格行出现
      await waitFor(() => {
        expect(screen.getByText('招商银行')).toBeInTheDocument();
      });
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
      // 注意：message.success 中也包含"共 2 只"，要用 ^...$ 精确匹配
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
      // 用正则匹配避免硬编码
      const row = screen.getByText('招商银行').closest('tr')!;
      const cells = within(row).getAllByText(/亿$/);
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('A12: 重置清空非 context 状态', () => {
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
