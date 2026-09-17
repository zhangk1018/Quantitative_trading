// tests/config/SellStrategyManager.test.tsx — 自编卖出策略管理区块（系统设置 → 自编指标 → 卖出策略）
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import SellStrategyManager from '../../src/features/config/components/SellStrategyManager';
import {
  saveCustomSellStrategy,
  listCustomSellStrategies,
} from '../../src/features/backtest/utils/customSellStrategyStorage';

// Mock @monaco-editor/react（与 CustomIndicatorManager.test.tsx 一致）
vi.mock('@monaco-editor/react', () => ({
  __esModule: true,
  default: function MockEditor(props: any) {
    const { value, onChange, onMount } = props;
    if (onMount) {
      onMount({
        getPosition: () => ({ lineNumber: 1, column: 1 }),
        executeEdits: () => {},
        setPosition: () => {},
        focus: () => {},
        onDidBlurEditorWidget: () => {},
      });
    }
    return (
      <textarea
        data-testid="monaco-editor"
        value={value ?? ''}
        onChange={(e) => onChange?.(e.target.value)}
        rows={4}
        style={{ width: '100%' }}
      />
    );
  },
  loader: { config: vi.fn() },
}));

describe('SellStrategyManager（系统设置卖出策略区块）', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('首次挂载自动创建预置卖出策略（调仓换股 / 分层止盈）', () => {
    render(<SellStrategyManager />);
    expect(screen.getByRole('button', { name: /新建卖出策略/ })).toBeTruthy();
    expect(screen.getByText('调仓换股')).toBeTruthy();
    expect(screen.getByText('分层止盈')).toBeTruthy();
    expect(document.body.textContent).toContain('已有 2 条');
  });

  it('已保存的策略出现在列表中（与预置策略共存）', () => {
    saveCustomSellStrategy({
      name: '跌破5日线卖出',
      formula: 'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [0]*len(close_prices)',
      operator: '>=',
      defaultThreshold: 1,
      description: 'desc',
    });
    render(<SellStrategyManager />);
    expect(screen.getByText('跌破5日线卖出')).toBeTruthy();
    expect(screen.getByText('调仓换股')).toBeTruthy();
    expect(document.body.textContent).toContain('已有 3 条');
  });

  it('填写表单并创建策略后列表更新', async () => {
    render(<SellStrategyManager />);
    // 先点击「新建卖出策略」打开 Drawer，再填写表单
    fireEvent.click(screen.getByRole('button', { name: /新建卖出策略/ }));
    await waitFor(() => {
      expect(screen.getByPlaceholderText('如：跌破5日均线卖出')).toBeTruthy();
    });
    fireEvent.change(screen.getByPlaceholderText('如：跌破5日均线卖出'), {
      target: { value: '新高回落卖出' },
    });
    // Monaco Editor 由 mock 渲染为 textarea（无 placeholder），用 data-testid 定位
    fireEvent.change(
      screen.getByTestId('monaco-editor'),
      { target: { value: 'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [0]*len(close_prices)' } },
    );
    // Drawer 内「创建」按钮（可访问名只有「创建」二字，用 data-testid 定位更稳）
    await waitFor(() => {
      expect(screen.getByTestId('sell-strategy-modal-confirm')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('sell-strategy-modal-confirm'));
    await waitFor(() => {
      // 2 条预置 + 1 条新建 = 3 条
      expect(listCustomSellStrategies()).toHaveLength(3);
    });
    expect(screen.getByText('新高回落卖出')).toBeTruthy();
  });
});