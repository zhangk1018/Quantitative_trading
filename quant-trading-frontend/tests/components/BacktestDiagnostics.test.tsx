// components/BacktestDiagnostics.test.tsx — 诊断面板渲染测试
// 覆盖：空数据/多事件类型/分组展示/时间线渲染

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import BacktestDiagnostics from '../../src/features/backtest/BacktestDiagnostics';
import type { DiagnosticEntry } from '../../src/features/backtest/backtestTypes';

// ==================== 测试数据 ====================

function makeEntry(
  event: DiagnosticEntry['event'],
  time: string,
  reason: string,
  data?: Record<string, unknown>,
): DiagnosticEntry {
  return { time, event, reason, data };
}

// ==================== 测试用例 ====================

describe('BacktestDiagnostics - 渲染', () => {
  it('空列表应显示"无诊断记录"', () => {
    render(<BacktestDiagnostics diagnostics={[]} />);
    expect(screen.getByText('无诊断记录')).toBeDefined();
  });

  it('undefined 应向空列表一样处理', () => {
    render(<BacktestDiagnostics diagnostics={undefined as any} />);
    expect(screen.getByText('无诊断记录')).toBeDefined();
  });

  it('有诊断记录时应显示总数', () => {
    const entries: DiagnosticEntry[] = [
      makeEntry('buy_signal', '2025-01-15', '自编指标 "MA5上穿MA20" 发出买入信号'),
      makeEntry('buy_executed', '2025-01-16', '执行买入 1000 股 @ 10.50'),
    ];
    render(<BacktestDiagnostics diagnostics={entries} />);
    expect(screen.getByText('诊断报告（共 2 条）')).toBeDefined();
  });

  it('应显示事件类型标签', () => {
    const entries: DiagnosticEntry[] = [
      makeEntry('buy_signal', '2025-01-15', '买入信号'),
      makeEntry('sell_signal', '2025-01-20', 'MA5下穿MA20 发出卖出信号'),
      makeEntry('buy_executed', '2025-01-16', '买入执行'),
      makeEntry('sell_executed', '2025-01-21', '卖出执行'),
      makeEntry('forced_close', '2025-12-31', '期末强制清仓'),
    ];
    render(<BacktestDiagnostics diagnostics={entries} />);

    expect(screen.getByText('买入信号')).toBeDefined();
    expect(screen.getByText('卖出信号')).toBeDefined();
    expect(screen.getByText('买入执行')).toBeDefined();
    expect(screen.getByText('卖出执行')).toBeDefined();
    expect(screen.getByText('强制清仓')).toBeDefined();
  });

  it('应显示每种事件类型的次数', () => {
    const entries: DiagnosticEntry[] = [
      makeEntry('buy_signal', '2025-01-15', '信号1'),
      makeEntry('buy_signal', '2025-02-15', '信号2'),
      makeEntry('buy_signal', '2025-03-15', '信号3'),
      makeEntry('sell_signal', '2025-04-15', '信号4'),
    ];
    render(<BacktestDiagnostics diagnostics={entries} />);

    // 买入信号应显示 3 次
    expect(screen.getByText('3 次')).toBeDefined();
    // 卖出信号应显示 1 次
    expect(screen.getByText('1 次')).toBeDefined();
  });

  it('应显示诊断原因和时间', () => {
    const entries: DiagnosticEntry[] = [
      makeEntry('buy_executed', '2025-06-15', '执行买入 500 股 @ 12.00', { shares: 500, price: 12.0 }),
    ];
    render(<BacktestDiagnostics diagnostics={entries} />);

    // Collapse 默认关闭，先点击展开
    const header = screen.getByText('买入执行').closest('.ant-collapse-header');
    fireEvent.click(header!);

    expect(screen.getByText('2025-06-15')).toBeDefined();
    expect(screen.getByText('执行买入 500 股 @ 12.00')).toBeDefined();
  });

  it('应显示附加数据字段', () => {
    const entries: DiagnosticEntry[] = [
      makeEntry('insufficient_funds', '2025-07-01', '资金不足 1 手', { required: 12000, available: 5000 }),
    ];
    render(<BacktestDiagnostics diagnostics={entries} />);

    // Collapse 默认关闭，先点击展开
    const header = screen.getByText('资金不足').closest('.ant-collapse-header');
    fireEvent.click(header!);

    expect(screen.getByText('资金不足 1 手')).toBeDefined();
    // 宽松匹配，不依赖 toFixed(2) 精度
    expect(screen.getByText(/required=12000/)).toBeDefined();
    expect(screen.getByText(/available=5000/)).toBeDefined();
  });

  it('script_error 应显示诊断信息', () => {
    const entries: DiagnosticEntry[] = [
      makeEntry('script_error', '2025-08-01', '自编指标执行失败：语法错误', { indicatorName: '测试指标' }),
    ];
    render(<BacktestDiagnostics diagnostics={entries} />);

    // Collapse 默认关闭，先点击展开
    const header = screen.getByText('脚本错误').closest('.ant-collapse-header');
    fireEvent.click(header!);

    expect(screen.getByText('脚本错误')).toBeDefined();
    expect(screen.getByText('自编指标执行失败：语法错误')).toBeDefined();
  });
});

describe('BacktestDiagnostics - 边界条件', () => {
  it('大量诊断条目应正常渲染', () => {
    const entries: DiagnosticEntry[] = Array.from({ length: 100 }, (_, i) =>
      makeEntry(
        i % 2 === 0 ? 'buy_signal' : 'sell_signal',
        `2025-${String(Math.floor(i / 30) + 1).padStart(2, '0')}-${String((i % 28) + 1).padStart(2, '0')}`,
        `信号 ${i}`,
      ),
    );
    render(<BacktestDiagnostics diagnostics={entries} />);
    expect(screen.getByText('诊断报告（共 100 条）')).toBeDefined();
  });

  it('所有事件类型均应正确渲染', () => {
    const allEvents: DiagnosticEntry['event'][] = [
      'buy_signal', 'sell_signal', 'buy_executed', 'sell_executed',
      'forced_close', 'buy_deferred', 'sell_deferred', 'buy_expired',
      'sell_expired', 'insufficient_funds', 'unexecuted_buy', 'script_error',
    ];
    const entries: DiagnosticEntry[] = allEvents.map((event) =>
      makeEntry(event, '2025-01-01', `事件: ${event}`),
    );
    render(<BacktestDiagnostics diagnostics={entries} />);
    expect(screen.getByText('诊断报告（共 12 条）')).toBeDefined();
  });

  it('null/undefined 的 data 字段不应导致渲染失败', () => {
    const entries: DiagnosticEntry[] = [
      { time: '2025-01-01', event: 'buy_signal', reason: '信号', data: { shares: null, price: undefined } as any },
    ];
    render(<BacktestDiagnostics diagnostics={entries} />);
    // Collapse 默认关闭，内部文本不可见，验证外层摘要渲染即可
    expect(screen.getByText('诊断报告（共 1 条）')).toBeDefined();
    // 验证事件类型标签可见
    expect(screen.getByText('买入信号')).toBeDefined();
  });
});