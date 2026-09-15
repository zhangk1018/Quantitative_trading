// tests/config/SellStrategyManager.test.tsx — 自编卖出策略管理区块（系统设置 → 自编指标 → 卖出策略）
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import SellStrategyManager from '../../src/features/config/components/SellStrategyManager';
import {
  saveCustomSellStrategy,
  listCustomSellStrategies,
} from '../../src/features/backtest/utils/customSellStrategyStorage';

describe('SellStrategyManager（系统设置卖出策略区块）', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('空列表显示空提示 + 新建卖出策略按钮', () => {
    render(<SellStrategyManager />);
    expect(screen.getByRole('button', { name: /新建卖出策略/ })).toBeTruthy();
    expect(document.body.textContent).toContain('暂无自编卖出策略');
  });

  it('已保存的策略出现在列表中', () => {
    saveCustomSellStrategy({
      name: '跌破5日线卖出',
      formula: 'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [0]*len(close_prices)',
      operator: '>=',
      defaultThreshold: 1,
      description: 'desc',
    });
    render(<SellStrategyManager />);
    expect(screen.getByText('跌破5日线卖出')).toBeTruthy();
    expect(document.body.textContent).toContain('已有 1 条');
  });

  it('填写表单并创建策略后列表更新', async () => {
    render(<SellStrategyManager />);
    fireEvent.change(screen.getByPlaceholderText('如：跌破5日均线卖出'), {
      target: { value: '新高回落卖出' },
    });
    fireEvent.change(
      screen.getByPlaceholderText(/def calculate\(open_prices/),
      { target: { value: 'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [0]*len(close_prices)' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /创建策略/ }));
    await waitFor(() => {
      expect(listCustomSellStrategies()).toHaveLength(1);
    });
    expect(screen.getByText('新高回落卖出')).toBeTruthy();
  });
});