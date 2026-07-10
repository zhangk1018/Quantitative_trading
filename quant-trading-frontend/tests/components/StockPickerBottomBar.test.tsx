import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StockPickerBottomBar } from '@/features/stock-picker/components/StockPickerBottomBar';

describe('StockPickerBottomBar', () => {
  it('显示已选中的股票数量', () => {
    render(
      <StockPickerBottomBar
        selectedCount={3}
        loading={false}
        itemsLength={10}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByText('已选中 3 只')).toBeInTheDocument();
  });

  it('未选中时显示提示文字', () => {
    render(
      <StockPickerBottomBar
        selectedCount={0}
        loading={false}
        itemsLength={10}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByText('未选中（点击左侧复选框多选）')).toBeInTheDocument();
  });

  it('添加自选按钮显示选中数量', () => {
    render(
      <StockPickerBottomBar
        selectedCount={5}
        loading={false}
        itemsLength={20}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    const btn = screen.getByTestId('add-to-watchlist-btn');
    expect(btn).toHaveTextContent('添加自选(5)');
  });

  it('loading 时添加自选按钮 disabled', () => {
    render(
      <StockPickerBottomBar
        selectedCount={3}
        loading={true}
        itemsLength={10}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByTestId('add-to-watchlist-btn')).toBeDisabled();
  });

  it('导出结果按钮显示数量', () => {
    render(
      <StockPickerBottomBar
        selectedCount={0}
        loading={false}
        itemsLength={15}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    const btn = screen.getByTestId('export-result-btn');
    expect(btn).toHaveTextContent('导出结果(15)');
  });

  it('无数据时导出按钮 disabled', () => {
    render(
      <StockPickerBottomBar
        selectedCount={0}
        loading={false}
        itemsLength={0}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByTestId('export-result-btn')).toBeDisabled();
  });

  it('无数据时刷新按钮 disabled', () => {
    render(
      <StockPickerBottomBar
        selectedCount={0}
        loading={false}
        itemsLength={0}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByTestId('refresh-result-btn')).toBeDisabled();
  });

  it('点击刷新按钮触发 onRefresh', async () => {
    const onRefresh = vi.fn();
    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    render(
      <StockPickerBottomBar
        selectedCount={0}
        loading={false}
        itemsLength={10}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={onRefresh}
      />
    );
    await user.click(screen.getByTestId('refresh-result-btn'));
    expect(onRefresh).toHaveBeenCalled();
  });

  it('渲染所有操作按钮', () => {
    render(
      <StockPickerBottomBar
        selectedCount={0}
        loading={false}
        itemsLength={0}
        onAddToWatchlist={vi.fn()}
        onExport={vi.fn()}
        onRefresh={vi.fn()}
      />
    );
    expect(screen.getByText('加入回测列表')).toBeInTheDocument();
    expect(screen.getByText('加入黑名单')).toBeInTheDocument();
    expect(screen.getByTestId('add-to-watchlist-btn')).toBeInTheDocument();
    expect(screen.getByTestId('export-result-btn')).toBeInTheDocument();
    expect(screen.getByTestId('refresh-result-btn')).toBeInTheDocument();
  });
});