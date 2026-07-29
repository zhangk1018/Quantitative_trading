// components/BacktestErrorBoundary.test.tsx — 错误边界测试
// 覆盖：正常渲染/错误捕获/重置/自定义标题

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BacktestErrorBoundary } from '../../src/features/backtest/ErrorBoundary';

// 抑制 console.error（测试中预期会触发 React 错误日志）
let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  consoleErrorSpy.mockRestore();
});

// ==================== 辅助组件 ====================

/** 正常渲染的子组件 */
function HealthyChild() {
  return <div data-testid="healthy">正常内容</div>;
}

/** 会抛出错误的子组件 */
function BuggyChild({ message = '测试错误' }: { message?: string }) {
  throw new Error(message);
}

// ==================== 测试用例 ====================

describe('BacktestErrorBoundary - 正常渲染', () => {
  it('应正常渲染子组件', () => {
    render(
      <BacktestErrorBoundary>
        <HealthyChild />
      </BacktestErrorBoundary>,
    );
    expect(screen.getByTestId('healthy')).toBeDefined();
    expect(screen.getByText('正常内容')).toBeDefined();
  });

  it('应正常渲染嵌套子组件', () => {
    render(
      <BacktestErrorBoundary>
        <div>
          <span>嵌套</span>
          <HealthyChild />
        </div>
      </BacktestErrorBoundary>,
    );
    expect(screen.getByText('嵌套')).toBeDefined();
    expect(screen.getByText('正常内容')).toBeDefined();
  });
});

describe('BacktestErrorBoundary - 错误捕获', () => {
  it('子组件抛出错误时应显示错误界面', () => {
    render(
      <BacktestErrorBoundary>
        <BuggyChild />
      </BacktestErrorBoundary>,
    );

    expect(screen.getByText('回测结果渲染失败')).toBeDefined();
    expect(screen.getByText('测试错误')).toBeDefined();
    expect(screen.getByText('重置并重试')).toBeDefined();
  });

  it('应使用自定义错误标题', () => {
    render(
      <BacktestErrorBoundary errorTitle="自定义错误标题">
        <BuggyChild message="内容错误" />
      </BacktestErrorBoundary>,
    );

    expect(screen.getByText('自定义错误标题')).toBeDefined();
    expect(screen.getByText('内容错误')).toBeDefined();
  });

  it('错误信息为空时应显示默认消息', () => {
    render(
      <BacktestErrorBoundary>
        <BuggyChild message="" />
      </BacktestErrorBoundary>,
    );

    expect(screen.getByText('回测结果渲染失败')).toBeDefined();
  });
});

describe('BacktestErrorBoundary - 重置', () => {
  it('点击重置按钮应调用 onReset 回调', () => {
    const onReset = vi.fn();
    render(
      <BacktestErrorBoundary onReset={onReset}>
        <BuggyChild />
      </BacktestErrorBoundary>,
    );

    const resetBtn = screen.getByText('重置并重试');
    fireEvent.click(resetBtn);

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('未提供 onReset 时点击重置按钮不应崩溃', () => {
    render(
      <BacktestErrorBoundary>
        <BuggyChild />
      </BacktestErrorBoundary>,
    );

    const resetBtn = screen.getByText('重置并重试');
    // 不应抛出错误
    expect(() => fireEvent.click(resetBtn)).not.toThrow();
  });
});

describe('BacktestErrorBoundary - 边界条件', () => {
  it('多个子组件中某个抛出错误应捕获', () => {
    render(
      <BacktestErrorBoundary>
        <HealthyChild />
        <BuggyChild />
      </BacktestErrorBoundary>,
    );

    // 整个树被错误边界替换，所以不应看到正常内容
    expect(screen.getByText('回测结果渲染失败')).toBeDefined();
  });

  it('深度嵌套的错误应被捕获', () => {
    function DeepBuggy() {
      return (
        <div>
          <div>
            <div>
              <BuggyChild message="深度错误" />
            </div>
          </div>
        </div>
      );
    }

    render(
      <BacktestErrorBoundary>
        <DeepBuggy />
      </BacktestErrorBoundary>,
    );

    expect(screen.getByText('深度错误')).toBeDefined();
  });
});