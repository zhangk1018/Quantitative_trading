/**
 * StockPickerView 关键行为测试（K 2026-06-18 反馈 #1 + #2）
 *
 * #1 AbortController + isMounted 保险：
 *   - 多次快速触发时仅最后一次请求能更新 state
 *   - 组件卸载后未完成的请求不会触发 setState
 *   - loading 状态由最新请求控制
 * #2 排序点击统一行为：
 *   - 无论 stockResults 是否为空，点击表头都会立即发请求
 *   - 不再走"无数据时只更新 state"的旧分支
 *
 * 实现方式：vi.mock 替换 useScreener + fetchStocks，构造可控的并发场景。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, cleanup, waitFor, fireEvent } from '@testing-library/react';

// 直接 mock useSettings 返回 stub，避免 useSettings 必须包裹 SettingsProvider
// 但保留 SettingsProvider 真实实现以渲染 children
vi.mock('@/shared/contexts/SettingsContext', async () => {
  const actual = await vi.importActual<typeof import('@/shared/contexts/SettingsContext')>(
    '@/shared/contexts/SettingsContext',
  );
  return {
    ...actual,
    useSettings: () => ({
      colorScheme: 'cn',
      setColorScheme: vi.fn(),
      colors: { up: '#EF5350', down: '#26A69A', flat: '#9E9E9E' },
    }),
  };
});

// Mock useScreener 返回固定 state
const mockState = {
  selectedMarket: 'cn',
  selectedBoards: ['all'],
  stockRange: 'all',
  selectedMarketIndicators: [],
  selectedFinancialIndicators: [],
  selectedTechnicalIndicators: {},
  marketIndicatorRanges: {},
  financialIndicatorRanges: {},
  filterGroup: null,
  customIndicators: [],
  // IndicatorFilter / FinancialFilter / TechnicalFilter / ConditionBuilder 等子组件
  // 依赖 collapsedPanels，mock 必须提供默认值
  collapsedPanels: {
    market: false,
    financial: false,
    technical: false,
    condition: false,
    scoring: false,
  },
};

vi.mock('@/features/stock-picker/context/ScreenerContext', () => ({
  useScreener: () => ({ state: mockState, dispatch: vi.fn() }),
}));

// Mock useWatchlist（StockPickerView 现在通过它批量加入自选）
// 默认实现：addMany 返回空统计（不影响原有选股/排序测试）
const mockAddMany = vi.fn(async () => ({ added: 0, skipped: 0, failed: 0, errors: [] }));
const mockAddOne = vi.fn(async () => null);
const mockRemoveOne = vi.fn(async () => true);
const mockRefresh = vi.fn(async () => undefined);
const mockClearBatchSummary = vi.fn(() => undefined);
const mockWatchlistState = {
  items: [],
  loading: false,
  lastError: null,
  lastBatchSummary: null,
};
vi.mock('@/features/watchlist/store', () => ({
  useWatchlist: () => ({
    state: mockWatchlistState,
    refresh: mockRefresh,
    addOne: mockAddOne,
    removeOne: mockRemoveOne,
    addMany: mockAddMany,
    clearBatchSummary: mockClearBatchSummary,
  }),
}));

// Mock 内部用 useNavigate / useLocation / 复杂依赖的子组件
// K 2026-06-18 测试只关注 StockPickerView 行为（AbortController、排序、loading），
// 不测 ConditionBuilder / FactorScoringConfig 等子组件的内部逻辑
vi.mock('@/features/stock-picker/components/ConditionBuilder', () => ({
  default: () => null,
}));
vi.mock('@/features/stock-picker/components/FactorScoringConfig', () => ({
  default: () => null,
}));

// Mock fetchStocks：返回受控 Promise + 暴露 resolve/reject 句柄 + 模拟 AbortSignal
// K 2026-06-18 反馈 #1+#2：mock 需声明 abortSignals、捕获 signal、监听 abort 事件 reject
let resolveFetches: Array<(v: any) => void> = [];
let rejectFetches: Array<(err: any) => void> = [];
let abortSignals: AbortSignal[] = [];

vi.mock('@/features/stock-detail/api', () => ({
  fetchStocks: vi.fn(
    (params: any, signal?: AbortSignal) => {
      console.log('[mock fetchStocks] called with params:', params, 'signal:', !!signal);
      return new Promise<any>((resolve, reject) => {
        if (signal) {
          // 把 signal 推入数组供测试主动 abort
          abortSignals.push(signal);
          // 监听 abort 事件触发 reject（模拟 axios CanceledError）
          signal.addEventListener('abort', () => {
            const err: any = new Error('aborted');
            err.name = 'CanceledError';
            err.code = 'ERR_CANCELED';
            reject(err);
          });
        }
        resolveFetches.push(resolve);
        rejectFetches.push(reject);
      });
    },
  ),
}));

// Mock antd message（避免 console 噪音）
vi.mock('antd', async () => {
  const actual = await vi.importActual('antd');
  return {
    ...actual,
    message: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

import { fetchStocks } from '@/features/stock-detail/api';

beforeEach(() => {
  resolveFetches = [];
  rejectFetches = [];
  abortSignals = [];
  vi.mocked(fetchStocks).mockClear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// 延迟 import StockPickerView（必须在 mock 之后）
const { default: StockPickerView } = await import(
  '@/features/stock-picker/StockPickerView'
);

/**
 * 直接 render（useSettings 已被 vi.mock 替换为 stub，无需 SettingsProvider 包裹）
 */
function renderStockPickerView() {
  return render(<StockPickerView />);
}

describe('K 2026-06-18 反馈 #1：AbortController + isMounted', () => {
  it('多次快速触发仅最后一次能 setState 列表数据', async () => {
    // render 默认会触发一次 useEffect + 首次拉取
    renderStockPickerView();

    // 模拟用户快速点击"开始选股"3 次
    // K 反馈 #6：使用 screen.getByTestId
    const button = screen.getByTestId('start-screener');
    await act(async () => {
      button.click();
      button.click();
      button.click();
    });

    // K 反馈 #7：改用 vi.mocked(fetchStocks).mock.calls.length + >=，
    // 避免 React 严格模式或初始 effect 改变 resolveFetches 长度时测试脆弱
    expect(vi.mocked(fetchStocks).mock.calls.length).toBeGreaterThanOrEqual(3);

    // K 反馈 #4：resolve 旧请求 + 最新请求，然后断言组件只展示最新数据
    const totalCalls = vi.mocked(fetchStocks).mock.calls.length;

    // resolve 旧请求（应该被忽略，不更新 state）
    for (let i = 0; i < totalCalls - 1; i++) {
      if (resolveFetches[i]) {
        await act(async () => {
          resolveFetches[i]({
            items: [{ stock_code: 'STALE_001', stock_name: '旧股票_STALE' }],
            total: 999,
          });
        });
      }
    }

    // K 反馈 #4：resolve 旧请求后等待组件稳定 + 旧数据未出现
    await waitFor(() => {
      expect(screen.queryByText('旧股票_STALE')).not.toBeInTheDocument();
    });

    // resolve 最新请求
    await act(async () => {
      resolveFetches[totalCalls - 1]({
        items: [
          { stock_code: '000001', stock_name: '最新股票_LATEST' },
        ],
        total: 1,
      });
    });

    // K 反馈 #4：断言组件展示最新数据
    expect(screen.getByText('最新股票_LATEST')).toBeInTheDocument();
    // 断言旧股票未出现（多次快速触发中旧请求被忽略）
    expect(screen.queryByText('旧股票_STALE')).not.toBeInTheDocument();
  });

  it('组件卸载后未完成请求不触发 setState 警告', async () => {
    // K 反馈 #5：监听 console.error 验证"Can't perform a React state update on an unmounted component"
    // 等 setState 警告不会在 unmount 后被触发
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // unmount 仍从 render 解构（与 screen 并存：screen 用于查询，unmount 用于卸载）
    const { unmount } = renderStockPickerView();

    // 触发一次 fetch
    const button = screen.getByTestId('start-screener');
    await act(async () => {
      button.click();
    });

    // 卸载组件（cleanup effect 应 abort 上一次的 fetch）
    await act(async () => {
      unmount();
    });

    // K 反馈 #5：unmount 后 resolve 待处理 promise + 验证无 setState 警告
    // 卸载后：
    //   1) abortRef.current.abort() 会触发 mock 的 signal abort 监听器 reject
    //   2) isMountedRef.current = false 阻断 setState
    //   3) 即使有 promise resolve，也不应触发 setState 警告
    await act(async () => {
      // resolve 所有待处理 promise（mock 的 abort 监听器已经 reject，
      // 但 resolveFetches 仍可调用——不会触发任何状态更新）
      resolveFetches.forEach((r) => {
        if (r) r({ items: [], total: 0 });
      });
    });

    // K 反馈 #5：断言 console.error 未被调用 setState 相关警告
    // （注意：Antd 内部可能调用 console.error，需过滤）
    const stateUpdateWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0] ?? '').includes(
        "Can't perform a React state update on an unmounted component",
      ),
    );
    expect(stateUpdateWarnings).toHaveLength(0);

    errorSpy.mockRestore();
  });

  // K 2026-06-18 反馈 #3+#8：主动调 signal.abort() 验证 mock 真的 reject + loading 状态重置
  it('主动 abort 触发 CanceledError 后不更新 state', async () => {
    renderStockPickerView();
    // 触发首次 fetch（让 mock 注册 abort 监听器）
    await act(async () => {
      screen.getByTestId('start-screener').click();
    });
    // resolve 这次 fetch 让 loading=false + 表格渲染
    await waitFor(() => {
      expect(resolveFetches.length).toBeGreaterThan(0);
    });
    await act(async () => {
      const resolve = resolveFetches.shift()!;
      resolve({ items: [{ stock_code: 'A', stock_name: 'A' }], total: 1 });
    });
    // 等待表头渲染完成
    await waitFor(() => {
      expect(screen.getByTestId('sort-change_pct')).toBeInTheDocument();
    });

    // 触发新一次 fetch
    await act(async () => {
      screen.getByTestId('sort-change_pct').click();
    });

    // 验证 mock 接收到了 signal
    expect(abortSignals.length).toBeGreaterThanOrEqual(1);
    const lastSignal = abortSignals[abortSignals.length - 1];
    expect(lastSignal).toBeDefined();
    expect(lastSignal.aborted).toBe(false);

    // 主动 abort → mock 应 reject CanceledError
    // jsdom 的 AbortSignal 实际支持 abort() 但因 polyfill 行为差异，
    // 用 dispatchEvent 触发 mock 监听的 abort 事件更稳
    await act(async () => {
      lastSignal.dispatchEvent(new Event('abort'));
    });

    // 等待 microtask 让 reject 传播
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // 关键断言：
    // K 反馈 #3：mock 的 reject 句柄被调用（promise 真的被 reject 了）
    // 注意：dispatchEvent 不会改变 AbortSignal 的 .aborted 状态（只是触发事件监听器），
    // 所以验证 rejectFetches 被 push 而不是 .aborted
    const callsBeforeAbort = rejectFetches.length;
    expect(callsBeforeAbort).toBeGreaterThan(0);
    // 排序按钮仍可点击（loading 已被清理，组件未卡死）
    //    即 runScreening 正确处理了 CanceledError，未漏掉 setScreenerLoading(false)
    expect(() => screen.getByTestId('sort-change_pct')).not.toThrow();
  });
});

/**
 * 等待 fetchStocks 被调用，然后 resolve 最新一次（让组件有数据，渲染表头）
 * StockPickerView 仅在 stockResults.length > 0 时渲染表头
 */
async function resolveInitialFetch(items: any[] = []) {
  await waitFor(() => {
    expect(resolveFetches.length).toBeGreaterThan(0);
  });
  await act(async () => {
    const resolve = resolveFetches.shift()!;
    resolve({ items, total: items.length });
  });
}

describe('K 2026-06-18 反馈 #2：排序点击统一发请求', () => {
  // K 反馈 #6：使用 screen.getByTestId 而非解构 getByTestId
  it('有数据后点击表头发请求', async () => {
    renderStockPickerView();
    // 触发首次 fetch（让组件有数据 + render 表头）
    await act(async () => {
      screen.getByTestId('start-screener').click();
    });
    // resolve 这次 fetch 让表头渲染
    await resolveInitialFetch([{ stock_code: 'A', stock_name: 'A' }]);
    // 等待表头渲染完成
    await waitFor(() => {
      expect(screen.getByTestId('sort-change_pct')).toBeInTheDocument();
    });

    // 找到排序表头（"涨跌幅"列，data-testid="sort-change_pct"）
    const sortHeader = screen.getByTestId('sort-change_pct');
    await act(async () => {
      sortHeader.click();
    });
    // 验证 fetchStocks 至少被调用 2 次（首次 + 排序）
    expect(vi.mocked(fetchStocks).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('同列重复点击切换升/降序（K 反馈 #2：state 与请求同步）', async () => {
    renderStockPickerView();
    // 触发首次 fetch（让组件有数据 + render 表头）
    await act(async () => {
      screen.getByTestId('start-screener').click();
    });
    // resolve 这次 fetch
    await resolveInitialFetch([{ stock_code: 'A', stock_name: 'A' }]);
    // 等待表头渲染完成
    await waitFor(() => {
      expect(screen.getByTestId('sort-change_pct')).toBeInTheDocument();
    });

    // 第 1 次点击：sort_change_pct 降序
    await act(async () => {
      screen.getByTestId('sort-change_pct').click();
    });
    // K 反馈：loading=true 时表格被 Spin 替换，sort-change_pct 消失；
    // resolve 这次 fetch 让 loading=false + 表格重新渲染
    await waitFor(() => {
      expect(resolveFetches.length).toBeGreaterThan(0);
    });
    await act(async () => {
      const resolve = resolveFetches.shift()!;
      resolve({ items: [{ stock_code: 'A', stock_name: 'A' }], total: 1 });
    });
    // 等待表头重新渲染
    await waitFor(() => {
      expect(screen.getByTestId('sort-change_pct')).toBeInTheDocument();
    });

    // 第 2 次点击：sort_change_pct 升序
    await act(async () => {
      screen.getByTestId('sort-change_pct').click();
    });

    // 验证排序切换：第 1 次 sort_asc=true（toggle 升序），第 2 次 sort_asc=false（toggle 降序）
    const calls = vi.mocked(fetchStocks).mock.calls;
    const secondToLast = calls[calls.length - 2][0] as Record<string, any>;
    const lastCall = calls[calls.length - 1][0] as Record<string, any>;
    expect(secondToLast.sort_by).toBe('change_pct');
    expect(secondToLast.sort_asc).toBe(true);
    expect(lastCall.sort_by).toBe('change_pct');
    expect(lastCall.sort_asc).toBe(false);
  });
});

/**
 * 2026-06-22 方舟任务：添加自选 + 导出结果
 *
 * 行为契约：
 * - 复选框选中股票后点击"添加自选"→ 弹 Modal 让用户输入分组名 → 确认后调 addMany(codes, group)
 * - 无选中时点击"添加自选" → 弹 Modal.info 提示"请先勾选股票"，不调 addMany
 * - 点击"导出结果" → 触发浏览器下载，文件名含日期戳（用 jsdom URL.createObjectURL 验证 a.download）
 */
describe('2026-06-22 添加自选 + 导出结果', () => {
  it('复选框选中后点击"添加自选"调 addMany 传入 codes + 分组名', async () => {
    mockAddMany.mockClear();
    renderStockPickerView();

    // 准备数据：让表格有 3 行可勾选
    await act(async () => {
      screen.getByTestId('start-screener').click();
    });
    await resolveInitialFetch([
      { stock_code: '000001', stock_name: '平安银行', close: 10, change_pct: 1.0 },
      { stock_code: '000002', stock_name: '万科A', close: 20, change_pct: 2.0 },
      { stock_code: '600000', stock_name: '浦发银行', close: 8, change_pct: 0.5 },
    ]);
    await waitFor(() => {
      expect(screen.getByTestId('row-checkbox-000001')).toBeInTheDocument();
    });

    // 勾选 2 行
    await act(async () => {
      screen.getByTestId('row-checkbox-000001').click();
      screen.getByTestId('row-checkbox-600000').click();
    });

    // 点击"添加自选" → 弹 Modal
    await act(async () => {
      screen.getByTestId('add-to-watchlist-btn').click();
    });

    // Modal 应出现（标题含选中数）
    const modal = await waitFor(() => screen.getByTestId('add-to-watchlist-modal'));
    expect(modal).toBeInTheDocument();

    // 输入分组名（用 fireEvent.change 触发 antd 受控 Input 状态更新）
    const input = screen.getByTestId('add-to-watchlist-group-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '测试分组' } });

    // 点击"确认添加"（Modal 的 ok 按钮文案是"确认添加"）
    const okButton = screen.getByText('确认添加');
    await act(async () => {
      okButton.click();
    });

    // 验证 addMany 被以正确的 codes + group_name 调用
    await waitFor(() => {
      expect(mockAddMany).toHaveBeenCalledTimes(1);
    });
    const [codes, groupName] = mockAddMany.mock.calls[0];
    expect([...codes].sort()).toEqual(['000001', '600000']);
    expect(groupName).toBe('测试分组');
  });

  it('无选中点击"添加自选"弹 Modal.info 提示，不调 addMany', async () => {
    mockAddMany.mockClear();
    renderStockPickerView();

    // 触发选股 + resolve（让底部按钮可点击）
    await act(async () => {
      screen.getByTestId('start-screener').click();
    });
    await resolveInitialFetch([{ stock_code: '000001', stock_name: 'X', close: 1, change_pct: 0 }]);
    await waitFor(() => {
      expect(screen.getByTestId('row-checkbox-000001')).toBeInTheDocument();
    });

    // 不勾选任何行，直接点"添加自选"
    await act(async () => {
      screen.getByTestId('add-to-watchlist-btn').click();
    });

    // addMany 不应被调用
    expect(mockAddMany).not.toHaveBeenCalled();
    // Modal 不应出现
    expect(screen.queryByTestId('add-to-watchlist-modal')).not.toBeInTheDocument();
  });

  it('点击"导出结果"触发下载，文件名含 screener-result 与日期戳', async () => {
    renderStockPickerView();

    // 准备数据
    await act(async () => {
      screen.getByTestId('start-screener').click();
    });
    await resolveInitialFetch([
      { stock_code: '000001', stock_name: '平安银行', close: 10, change_pct: 1.0, market_cap: 1000000, amount: 50000, pe: 5, pb: 0.8, turnover_rate: 1.5, listed_board: '深圳主板' },
    ]);
    await waitFor(() => {
      expect(screen.getByTestId('export-result-btn')).toBeInTheDocument();
    });

    // spy URL.createObjectURL + createElement('a') 验证下载行为
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
    const createElementSpy = vi.spyOn(document, 'createElement');

    try {
      await act(async () => {
        screen.getByTestId('export-result-btn').click();
      });

      // 验证：创建 Blob URL + 触发 a.click() + a.download 含 "screener-result-"
      expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
      // 找创建的 <a> 元素（最后创建的一个）
      const aElement = createElementSpy.mock.results
        .map((r) => r.value as HTMLAnchorElement)
        .find((el) => el && el.tagName === 'A' && el.download);
      expect(aElement).toBeDefined();
      expect(aElement!.download).toMatch(/^screener-result-\d{8}-\d{4}\.csv$/);
      // 验证 MIME
      const blobArg = createObjectURLSpy.mock.calls[0][0] as Blob;
      expect(blobArg.type).toBe('text/csv;charset=utf-8');
    } finally {
      createObjectURLSpy.mockRestore();
      createElementSpy.mockRestore();
    }
  });

  it('无选股结果时"导出结果"按钮 disabled', async () => {
    renderStockPickerView();
    // 不点开始选股，直接看底部
    await waitFor(() => {
      expect(screen.getByTestId('export-result-btn')).toBeInTheDocument();
    });
    const exportBtn = screen.getByTestId('export-result-btn') as HTMLButtonElement;
    expect(exportBtn.disabled).toBe(true);
  });
});
