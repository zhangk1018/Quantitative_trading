/**
 * 自编指标列表组件测试（P3.3）
 *
 * 测试覆盖：
 * 1. 空状态
 * 2. 列表渲染（名称 / 分类 / 运算符 / 公式预览）
 * 3. 公式预览截断
 * 4. 编辑按钮触发 onEdit
 * 5. 删除按钮：未引用 → 直接确认
 * 6. 删除按钮：已引用 → Popconfirm 文案区分
 * 7. 阈值格式化（单值/双值）
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfigProvider } from 'antd';
import { CustomIndicatorList } from '@/features/stock-picker/components/CustomIndicatorList';
import { CustomIndicator } from '@/features/stock-picker/types/customIndicator';
import * as storage from '@/features/stock-picker/utils/customIndicatorStorage';

// ============================================================================
// Helpers
// ============================================================================

function makeIndicator(overrides: Partial<CustomIndicator> = {}): CustomIndicator {
  return {
    id: overrides.id ?? `ind_${Math.random().toString(36).slice(2, 8)}`,
    userId: 'mock_user_default',
    name: '测试指标',
    category: 'trend',
    syntax: 'tdx',
    formula: 'CLOSE > MA(CLOSE, 5)',
    params: [],
    operator: '>',
    defaultThreshold: 0,
    description: '',
    visibility: 'private',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

function renderList(props: Partial<React.ComponentProps<typeof CustomIndicatorList>> = {}) {
  const onEdit = props.onEdit ?? vi.fn();
  const onDelete = props.onDelete ?? vi.fn();
  const indicators = props.indicators ?? [];
  return render(
    <ConfigProvider>
      <CustomIndicatorList indicators={indicators} onEdit={onEdit} onDelete={onDelete} {...props} />
    </ConfigProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  storage.clearAllCustomIndicators();
});

// ============================================================================
// 1. 空状态
// ============================================================================

describe('CustomIndicatorList - 空状态', () => {
  it('空列表显示"暂无自编指标"提示', () => {
    renderList({ indicators: [] });
    expect(screen.getByTestId('custom-list-empty')).toHaveTextContent('暂无自编指标');
  });

  it('空列表时不渲染列表容器', () => {
    renderList({ indicators: [] });
    expect(screen.queryByTestId('custom-list')).not.toBeInTheDocument();
  });
});

// ============================================================================
// 2. 列表渲染
// ============================================================================

describe('CustomIndicatorList - 列表渲染', () => {
  it('渲染列表容器 + 每行指标', () => {
    const indicators = [
      makeIndicator({ id: 'a', name: '指标A' }),
      makeIndicator({ id: 'b', name: '指标B' }),
    ];
    renderList({ indicators });
    expect(screen.getByTestId('custom-list')).toBeInTheDocument();
    expect(screen.getByTestId('custom-list-item-a')).toBeInTheDocument();
    expect(screen.getByTestId('custom-list-item-b')).toBeInTheDocument();
  });

  it('显示指标名称 + 分类 Tag + 运算符 + 阈值 + 公式预览', () => {
    const ind = makeIndicator({
      id: 'a',
      name: 'MA20',
      category: 'trend',
      operator: '>',
      defaultThreshold: 100,
      formula: 'CLOSE > MA(CLOSE, 20)',
    });
    renderList({ indicators: [ind] });
    expect(screen.getByTestId('custom-list-item-name-a')).toHaveTextContent('MA20');
    // 分类 Tag 显示中文标签
    expect(screen.getByText('趋势类')).toBeInTheDocument();
    // 运算符 + 阈值
    expect(screen.getByTestId('custom-list-item-a').textContent).toContain('>');
    expect(screen.getByTestId('custom-list-item-a').textContent).toContain('100');
    // 公式预览（无截断，因 < 40 字符）
    expect(screen.getByTestId('custom-list-item-a').textContent).toContain('CLOSE > MA(CLOSE, 20)');
  });

  it('分类为震荡类时显示对应中文标签', () => {
    const ind = makeIndicator({ id: 'a', name: 'RSI自定义', category: 'oscillator' });
    renderList({ indicators: [ind] });
    expect(screen.getByText('震荡类')).toBeInTheDocument();
  });
});

// ============================================================================
// 3. 公式预览截断
// ============================================================================

describe('CustomIndicatorList - 公式预览', () => {
  it('公式长度 > 40 字符时显示截断（带 ...）', () => {
    const longFormula = 'A'.repeat(50);
    const ind = makeIndicator({ id: 'a', formula: longFormula });
    renderList({ indicators: [ind] });
    // 截断为 40 字符 + ...
    const code = screen.getByTestId('custom-list-item-a').querySelector('code');
    expect(code?.textContent).toBe('A'.repeat(40) + '...');
  });

  it('公式长度 ≤ 40 字符时不截断', () => {
    const ind = makeIndicator({ id: 'a', formula: 'CLOSE > 5' });
    renderList({ indicators: [ind] });
    const code = screen.getByTestId('custom-list-item-a').querySelector('code');
    expect(code?.textContent).toBe('CLOSE > 5');
    expect(code?.textContent).not.toContain('...');
  });
});

// ============================================================================
// 4. 编辑按钮
// ============================================================================

describe('CustomIndicatorList - 编辑按钮', () => {
  it('点击编辑按钮触发 onEdit 回调，传入指标对象', async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const ind = makeIndicator({ id: 'a', name: 'A' });
    renderList({ indicators: [ind], onEdit });

    await user.click(screen.getByTestId('custom-list-edit-a'));
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledWith(ind);
  });
});

// ============================================================================
// 5. 删除按钮 - 未引用
// ============================================================================

/** 等待 Popconfirm OK 按钮出现（K 2026-06-18 反馈 #9+#7）
 *  - 用 screen.getByTestId 找 Popconfirm 内部 button（K 反馈 #7 偏好）
 *  - Antd v5 Popconfirm 实际支持 okButtonProps.data-testid 透传到内部 button DOM
 *    （组件层 153 行的 `data-testid: \`custom-list-popconfirm-ok-${ind.id}\`` 已正确注入）
 *  - debug 实测：button DOM 含 data-testid="custom-list-popconfirm-ok-a"
 *  - 注意：button 文本是 "删 除"（中间有空格），不能用 getByRole('button', {name: '删除'})
 *  - 不依赖 Antd 内部 class（如 .ant-popconfirm），避免样式耦合
 */
async function waitForPopconfirmOk(id: string) {
  return waitFor(() => screen.getByTestId(`custom-list-popconfirm-ok-${id}`));
}

/** 等待 Popconfirm Cancel 按钮出现（同上） */
async function waitForPopconfirmCancel(id: string) {
  return waitFor(() => screen.getByTestId(`custom-list-popconfirm-cancel-${id}`));
}

describe('CustomIndicatorList - 删除未引用指标', () => {
  it('Popconfirm 文案为"确认删除该自编指标？"，确认后调用 onDelete', async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const ind = makeIndicator({ id: 'a' });
    // 不在 localStorage 中放置 plans 引用
    renderList({ indicators: [ind], onDelete });

    // 点击删除按钮
    await user.click(screen.getByTestId('custom-list-delete-a'));
    // 等待 Popconfirm 出现
    await waitFor(() => {
      expect(screen.getByText('确认删除该自编指标？')).toBeInTheDocument();
    });
    // 找到 OK 按钮并点击
    const okButton = await waitForPopconfirmOk('a');
    await user.click(okButton);

    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledWith('a');
  });

  it('取消 Popconfirm 不调用 onDelete', async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const ind = makeIndicator({ id: 'a' });
    renderList({ indicators: [ind], onDelete });

    await user.click(screen.getByTestId('custom-list-delete-a'));
    await waitFor(() => {
      expect(screen.getByText('确认删除该自编指标？')).toBeInTheDocument();
    });
    // 点击 Cancel 按钮
    const cancelButton = await waitForPopconfirmCancel('a');
    await user.click(cancelButton);

    expect(onDelete).not.toHaveBeenCalled();
  });
});

// ============================================================================
// 6. 删除按钮 - 已引用
// ============================================================================

describe('CustomIndicatorList - 删除已引用指标', () => {
  it('Popconfirm 文案提示"被方案引用"风险', async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const ind = makeIndicator({ id: 'a' });
    // K 2026-06-18 任务 #9：引用关系从 localStorage 改为 props 注入，
    // 测试通过 referencedIds={{ 'a' }} 显式告知组件被引用（不再依赖 localStorage）
    renderList({ indicators: [ind], referencedIds: new Set(['a']), onDelete });

    await user.click(screen.getByTestId('custom-list-delete-a'));
    await waitFor(() => {
      expect(screen.getByText('该指标被方案引用')).toBeInTheDocument();
    });
    expect(screen.getByText(/删除后引用该指标的条件将自动标记为失效/)).toBeInTheDocument();

    // 确认删除
    const okButton = await waitForPopconfirmOk('a');
    await user.click(okButton);
    expect(onDelete).toHaveBeenCalledWith('a');
  });
});

// ============================================================================
// 7. 阈值格式化
// ============================================================================

describe('CustomIndicatorList - 阈值显示', () => {
  it('单值阈值显示数字', () => {
    const ind = makeIndicator({ id: 'a', defaultThreshold: 50 });
    renderList({ indicators: [ind] });
    expect(screen.getByTestId('custom-list-item-a').textContent).toContain('50');
  });

  it('双值阈值显示为 [low, high] 区间', () => {
    const ind = makeIndicator({ id: 'a', defaultThreshold: [10, 80] });
    renderList({ indicators: [ind] });
    expect(screen.getByTestId('custom-list-item-a').textContent).toContain('[10, 80]');
  });
});
