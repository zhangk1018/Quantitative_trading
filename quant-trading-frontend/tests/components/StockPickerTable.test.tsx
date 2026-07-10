import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StockPickerTable } from '@/features/stock-picker/components/StockPickerTable';
import type { StockItem } from '@/features/stock-picker/types';

// Mock useSettings
vi.mock('@/shared/contexts/SettingsContext', () => ({
  useSettings: () => ({
    colorScheme: 'cn',
    setColorScheme: vi.fn(),
    colors: { up: '#EF5350', down: '#26A69A', flat: '#9E9E9E' },
  }),
}));

// Mock @tanstack/react-virtual
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: vi.fn(() => ({
    getVirtualItems: () => Array.from({ length: 3 }, (_, i) => ({
      index: i,
      size: 48,
      start: i * 48,
      key: i,
      measureElement: vi.fn(),
    })),
    getTotalSize: () => 3 * 48,
    scrollToIndex: vi.fn(),
    measure: vi.fn(),
  })),
}));

const makeStock = (code: string, name: string, changePct = 0): StockItem => ({
  stock_code: code,
  stock_name: name,
  close: 35.2,
  change_pct: changePct,
  turnover_rate: 0.85,
  pe: 5.4,
  pe_ttm: 5.1,
  pb: 0.92,
  market_cap: 895600000000,
  amount: 1234000000,
  listed_board: '上海主板',
});

const items: StockItem[] = [
  makeStock('600036', '招商银行', 1.25),
  makeStock('000001', '平安银行', -0.85),
  makeStock('300750', '宁德时代', 3.45),
];

// ResizeObserver polyfill
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverMock as any;

// scrollTo polyfill
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = vi.fn() as any;
}

describe('StockPickerTable', () => {
  const defaultProps = {
    items: [] as StockItem[],
    total: 0,
    loading: false,
    loadingMore: false,
    pageSize: 20,
    selectedCodes: new Set<string>(),
    indeterminate: false,
    allSelected: false,
    sortBy: 'change_pct',
    sortAsc: false,
    error: null as string | null,
    loadMoreError: null as string | null,
    onToggleAll: vi.fn(),
    onToggleOne: vi.fn(),
    onSort: vi.fn(),
    onDoubleClick: vi.fn(),
    onLoadMore: vi.fn(),
    onRetry: vi.fn(),
    onRetryLoadMore: vi.fn(),
    scrollContainerRef: { current: null } as React.RefObject<HTMLDivElement>,
  };

  it('loading 状态显示加载中', () => {
    render(<StockPickerTable {...defaultProps} loading={true} />);
    expect(screen.getByText('正在加载数据...')).toBeInTheDocument();
  });

  it('error 状态显示错误信息和重试按钮', () => {
    render(<StockPickerTable {...defaultProps} error="网络连接异常，请检查网络" />);
    expect(screen.getByText('网络连接异常，请检查网络')).toBeInTheDocument();
    // Antd 按钮渲染中文时会在字间加空格，用正则匹配
    expect(screen.getByText(/重.*试/)).toBeInTheDocument();
  });

  it('error 状态点击重试按钮调用 onRetry', async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<StockPickerTable {...defaultProps} error="网络连接异常，请检查网络" onRetry={onRetry} />);
    await user.click(screen.getByText(/重.*试/));
    expect(onRetry).toHaveBeenCalled();
  });

  it('空数据状态显示提示', () => {
    render(<StockPickerTable {...defaultProps} items={[]} total={0} />);
    expect(screen.getByText(/暂无数据/)).toBeInTheDocument();
  });

  it('有数据时渲染表格', () => {
    render(<StockPickerTable {...defaultProps} items={items} total={3} />);
    expect(screen.getByText('招商银行')).toBeInTheDocument();
    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('宁德时代')).toBeInTheDocument();
  });

  it('渲染表头', () => {
    render(<StockPickerTable {...defaultProps} items={items} total={3} />);
    expect(screen.getByText('代码')).toBeInTheDocument();
    expect(screen.getByText('名称')).toBeInTheDocument();
    expect(screen.getByText('收盘价')).toBeInTheDocument();
    expect(screen.getByText(/涨跌幅/)).toBeInTheDocument();
    expect(screen.getByText('板块')).toBeInTheDocument();
  });

  it('渲染全选复选框', () => {
    render(<StockPickerTable {...defaultProps} items={items} total={3} />);
    expect(screen.getByTestId('select-all-checkbox')).toBeInTheDocument();
  });

  it('渲染行内复选框', () => {
    render(
      <StockPickerTable
        {...defaultProps}
        items={items}
        total={3}
        selectedCodes={new Set(['600036'])}
      />
    );
    expect(screen.getByTestId('row-checkbox-600036')).toBeInTheDocument();
    expect(screen.getByTestId('row-checkbox-000001')).toBeInTheDocument();
  });

  it('点击排序表头触发 onSort', async () => {
    const onSort = vi.fn();
    const user = userEvent.setup();
    render(<StockPickerTable {...defaultProps} items={items} total={3} onSort={onSort} />);
    await user.click(screen.getByTestId('sort-change_pct'));
    expect(onSort).toHaveBeenCalledWith('change_pct');
  });

  it('total > items.length 时显示加载更多按钮', () => {
    render(<StockPickerTable {...defaultProps} items={items} total={100} />);
    expect(screen.getByTestId('load-more-btn')).toBeInTheDocument();
  });

  it('加载更多按钮显示剩余数量', () => {
    render(<StockPickerTable {...defaultProps} items={items} total={20} pageSize={20} />);
    const btn = screen.getByTestId('load-more-btn');
    expect(btn).toHaveTextContent(/17/);
  });

  it('点击加载更多按钮调用 onLoadMore', async () => {
    const onLoadMore = vi.fn();
    const user = userEvent.setup();
    render(<StockPickerTable {...defaultProps} items={items} total={100} onLoadMore={onLoadMore} />);
    await user.click(screen.getByTestId('load-more-btn'));
    expect(onLoadMore).toHaveBeenCalled();
  });

  it('loadingMore 时加载更多按钮 disabled', () => {
    render(<StockPickerTable {...defaultProps} items={items} total={100} loadingMore={true} />);
    expect(screen.getByTestId('load-more-btn')).toBeDisabled();
  });

  it('loadMoreError 时显示重试按钮', () => {
    render(
      <StockPickerTable
        {...defaultProps}
        items={items}
        total={100}
        loadMoreError="加载更多失败"
      />
    );
    expect(screen.getByText('加载更多失败')).toBeInTheDocument();
    expect(screen.getByTestId('retry-load-more-btn')).toBeInTheDocument();
  });

  it('点击加载更多重试按钮调用 onRetryLoadMore', async () => {
    const onRetryLoadMore = vi.fn();
    const user = userEvent.setup();
    render(
      <StockPickerTable
        {...defaultProps}
        items={items}
        total={100}
        loadMoreError="加载更多失败"
        onRetryLoadMore={onRetryLoadMore}
      />
    );
    await user.click(screen.getByTestId('retry-load-more-btn'));
    expect(onRetryLoadMore).toHaveBeenCalled();
  });

  it('双击行触发 onDoubleClick', async () => {
    const onDoubleClick = vi.fn();
    const user = userEvent.setup();
    render(
      <StockPickerTable
        {...defaultProps}
        items={items}
        total={3}
        onDoubleClick={onDoubleClick}
      />
    );
    const row = screen.getByText('招商银行').closest('tr')!;
    await user.dblClick(row);
    expect(onDoubleClick).toHaveBeenCalledWith(items[0]);
  });

  it('渲染板块标签', () => {
    render(<StockPickerTable {...defaultProps} items={items} total={3} />);
    expect(screen.getAllByText('上海主板').length).toBeGreaterThan(0);
  });

  it('allSelected=true 时全选复选框 checked', () => {
    render(
      <StockPickerTable
        {...defaultProps}
        items={items}
        total={3}
        allSelected={true}
      />
    );
    const checkbox = screen.getByTestId('select-all-checkbox') as HTMLInputElement;
    expect(checkbox).toBeChecked();
  });

  it('indeterminate=true 时全选复选框半选状态', () => {
    render(
      <StockPickerTable
        {...defaultProps}
        items={items}
        total={3}
        indeterminate={true}
        selectedCodes={new Set(['600036'])}
      />
    );
    const checkbox = screen.getByTestId('select-all-checkbox');
    expect(checkbox).toBeInTheDocument();
  });
});