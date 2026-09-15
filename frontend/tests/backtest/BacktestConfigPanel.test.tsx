// tests/backtest/BacktestConfigPanel.test.tsx — 回测配置面板：自编卖出策略选择与 storage
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import BacktestConfigPanel from '../../src/features/backtest/BacktestConfigPanel';
import { WatchlistProvider } from '../../src/features/watchlist/store';
import {
  MOCK_USER_ID,
  saveCustomSellStrategy,
  listCustomSellStrategies,
} from '../../src/features/backtest/utils/customSellStrategyStorage';

describe('BacktestConfigPanel - 自编卖出策略', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('渲染「自编卖出策略可在系统设置中管理」提示（管理入口已迁移）', () => {
    render(
      <WatchlistProvider>
        <BacktestConfigPanel onStart={() => {}} loading={false} onCancel={() => {}} />
      </WatchlistProvider>,
    );
    // 面板仅保留提示文案，不再有管理按钮/弹窗
    expect(document.body.textContent).toContain('系统设置');
    expect(document.body.textContent).toContain('卖出策略');
  });

  it('通过 storage API 创建的策略可被 listCustomSellStrategies 读取（供选择下拉分组使用）', () => {
    saveCustomSellStrategy({
      name: '跌破5日线卖出',
      formula: 'def calculate(open_prices, high_prices, low_prices, close_prices, volumes):\n    return [0]*len(close_prices)',
      operator: '>=',
      defaultThreshold: 1,
      description: 'desc',
    });
    const list = listCustomSellStrategies();
    expect(list).toHaveLength(1);
    expect(list[0].name).toBe('跌破5日线卖出');
    expect(list[0].userId).toBe(MOCK_USER_ID);
  });
});