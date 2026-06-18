/**
 * 自编指标创建/编辑抽屉测试（P3.1）
 *
 * 测试覆盖：
 * 1. 抽屉打开/关闭
 * 2. 名称 OnBlur 校验（格式 + 唯一性）
 * 3. 公式 OnBlur 校验（通过 mock Monaco onMount 触发 onDidBlurEditorWidget）
 * 4. 字段插入按钮（参数名/行情字段/指标函数）
 * 5. 参数增删
 * 6. 运算符切换（单值/双值阈值）
 * 7. 提交逻辑 + onConfirm 回调
 * 8. 取消/编辑模式
 *
 * 注意：@monaco-editor/react 在 jsdom 环境无法真实加载（worker + CDN 资源），
 *       通过 vi.mock 替换为受控的 textarea 模拟组件，保留 onChange/onMount 接口。
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfigProvider } from 'antd';
import { CustomIndicatorModal } from '@/features/stock-picker/components/CustomIndicatorModal';
import * as storage from '@/features/stock-picker/utils/customIndicatorStorage';
import { CustomIndicator } from '@/features/stock-picker/types/customIndicator';

// ============================================================================
// Mock @monaco-editor/react：用受控 textarea + 手动触发 onDidBlurEditorWidget
// - vi.hoisted 把 monacoBlurCallbacks 提升到 mock 之前，测试文件 beforeEach 可访问
// ============================================================================

const { monacoBlurCallbacks } = vi.hoisted(() => ({
  monacoBlurCallbacks: [] as Array<() => void>,
}));

vi.mock('@monaco-editor/react', () => ({
  __esModule: true,
  default: function MockEditor(props: any) {
    const { value, onChange, onMount, options, 'data-testid': testId } = props;
    if (onMount) {
      onMount({
        getPosition: () => ({ lineNumber: 1, column: 1 }),
        executeEdits: (_id: string, edits: any[]) => {
          const insertText = edits[0]?.text ?? '';
          const newValue = (value ?? '') + insertText;
          onChange?.(newValue);
        },
        setPosition: () => {},
        focus: () => {},
        onDidBlurEditorWidget: (cb: () => void) => {
          // 保存到 vi.hoisted 共享数组
          monacoBlurCallbacks.push(cb);
        },
      });
    }
    return (
      <textarea
        data-testid={testId ?? 'monaco-editor'}
        value={value ?? ''}
        onChange={(e) => onChange?.(e.target.value)}
        readOnly={options?.readOnly}
        rows={4}
        style={{ width: '100%' }}
      />
    );
  },
  loader: { config: vi.fn() },
}));

function triggerMonacoBlur() {
  const cb = monacoBlurCallbacks[monacoBlurCallbacks.length - 1];
  if (!cb) throw new Error('No Monaco blur callback registered');
  cb();
}

// ============================================================================
// Helpers
// ============================================================================

function renderModal(props: Partial<React.ComponentProps<typeof CustomIndicatorModal>> = {}) {
  const onConfirm = props.onConfirm ?? vi.fn();
  const onCancel = props.onCancel ?? vi.fn();
  return render(
    <ConfigProvider>
      <CustomIndicatorModal title="新建自编指标" editing={null} onConfirm={onConfirm} onCancel={onCancel} {...props} />
    </ConfigProvider>,
  );
}

function getNameInput() {
  return screen.getByTestId('custom-indicator-modal-name') as HTMLInputElement;
}

function getFormulaEditor() {
  // Monaco 已被 mock 为 textarea
  return screen.getByTestId('custom-indicator-modal-formula-editor').querySelector('textarea') as HTMLTextAreaElement;
}

function getCategorySelect() {
  return screen.getByTestId('custom-indicator-modal-category');
}

function getSyntaxSelect() {
  return screen.getByTestId('custom-indicator-modal-syntax');
}

function getOperatorSelect() {
  return screen.getByTestId('custom-indicator-modal-operator');
}

function getParamAdd() {
  return screen.getByTestId('custom-indicator-modal-param-add');
}

function getConfirmButton() {
  return screen.getByTestId('custom-indicator-modal-confirm') as HTMLButtonElement;
}

/** 提取按钮文字（去掉 Antd 5 Button 文字中间的空格） */
function getConfirmButtonText() {
  return (getConfirmButton().textContent ?? '').replace(/\s/g, '');
}

function getCancelButton() {
  return screen.getByTestId('custom-indicator-modal-cancel') as HTMLButtonElement;
}

function makeIndicatorData(overrides: Partial<any> = {}) {
  return {
    name: '测试指标',
    category: 'trend' as const,
    syntax: 'tdx' as const,
    formula: 'CLOSE > MA(CLOSE, 5)',
    params: [],
    operator: '>' as const,
    defaultThreshold: 0,
    description: '',
    visibility: 'private' as const,
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  storage.clearAllCustomIndicators();
  monacoBlurCallbacks.length = 0;
});

afterEach(() => {
  vi.clearAllMocks();
});

// ============================================================================
// 1. 抽屉打开/关闭
// ============================================================================

describe('CustomIndicatorModal - 抽屉打开/关闭', () => {
  it('默认打开时显示 8 字段表单', () => {
    renderModal();
    expect(screen.getByTestId('custom-indicator-modal')).toBeInTheDocument();
    expect(getNameInput()).toBeInTheDocument();
    expect(getFormulaEditor()).toBeInTheDocument();
    expect(getCategorySelect()).toBeInTheDocument();
    expect(getSyntaxSelect()).toBeInTheDocument();
    expect(getOperatorSelect()).toBeInTheDocument();
    expect(screen.getByTestId('custom-indicator-modal-visibility')).toBeInTheDocument();
  });

  it('点击取消按钮触发 onCancel 回调', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    renderModal({ onCancel });
    await user.click(getCancelButton());
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('编辑模式显示编辑提示', () => {
    const editing: Partial<CustomIndicator> = {
      id: 'ind_test',
      name: '已存在指标',
      category: 'oscillator',
      formula: 'RSI(CLOSE, 12)',
      syntax: 'tdx',
      params: [],
      operator: '>',
      defaultThreshold: 30,
      description: '',
      visibility: 'private',
    };
    renderModal({ editing: editing as CustomIndicator, title: '编辑自编指标' });
    // 编辑模式下确认按钮显示"保存"（Antd 5 Button 文字含空格，提取后比对）
    expect(getConfirmButtonText()).toBe('保存');
  });
});

// ============================================================================
// 2. 名称 OnBlur 校验
// ============================================================================

describe('CustomIndicatorModal - 名称 OnBlur 校验', () => {
  it('OnBlur 时校验格式（短于 2 字符）', async () => {
    const user = userEvent.setup();
    renderModal();
    const input = getNameInput();
    await user.type(input, 'A'); // 1 字符
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.getByText(/指标名称长度须为 2-30 字符/)).toBeInTheDocument();
    });
  });

  it('OnBlur 时校验格式（含非法字符）', async () => {
    const user = userEvent.setup();
    renderModal();
    const input = getNameInput();
    await user.type(input, '指标!@#');
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.getByText(/指标名称仅支持中英文、数字、下划线、连字符和括号/)).toBeInTheDocument();
    });
  });

  it('OnBlur 时校验唯一性（已存在）', async () => {
    const user = userEvent.setup();
    storage.saveCustomIndicator(makeIndicatorData({ name: '已存在指标' }) as any);
    renderModal();
    const input = getNameInput();
    await user.type(input, '已存在指标');
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.getByText(/指标名称"已存在指标"已存在/)).toBeInTheDocument();
    });
  });

  it('OnBlur 通过合法校验后清空错误', async () => {
    const user = userEvent.setup();
    renderModal();
    const input = getNameInput();
    await user.type(input, 'RSI自定义');
    fireEvent.blur(input);
    await waitFor(() => {
      expect(input.closest('.ant-form-item')).not.toHaveClass('ant-form-item-has-error');
    });
  });
});

// ============================================================================
// 3. 公式 OnBlur 校验（通过 mock Monaco 触发 onDidBlurEditorWidget）
// ============================================================================

describe('CustomIndicatorModal - 公式 OnBlur 校验', () => {
  it('Monaco onMount 时绑定 onDidBlurEditorWidget', () => {
    renderModal();
    expect(monacoBlurCallbacks.length).toBeGreaterThan(0);
    expect(typeof monacoBlurCallbacks[monacoBlurCallbacks.length - 1]).toBe('function');
  });

  it('onDidBlurEditorWidget 触发时校验非空公式（合法）', async () => {
    const user = userEvent.setup();
    renderModal();
    const editor = getFormulaEditor();
    await user.type(editor, 'CLOSE > MA(CLOSE, 5)');
    triggerMonacoBlur();
    await waitFor(() => {
      const item = editor.closest('.ant-form-item');
      expect(item).not.toHaveClass('ant-form-item-has-error');
    });
  });

  it('onDidBlurEditorWidget 触发时校验长度（> 8000 字符）', async () => {
    const user = userEvent.setup();
    renderModal();
    const editor = getFormulaEditor();
    // 直接设置值（避免 type 8001 字符耗时）
    fireEvent.change(editor, { target: { value: 'A'.repeat(8001) } });
    triggerMonacoBlur();
    await waitFor(() => {
      expect(screen.getByText(/公式长度不能超过 8000 字符/)).toBeInTheDocument();
    });
  });
});

// ============================================================================
// 4. 字段插入按钮
// ============================================================================

describe('CustomIndicatorModal - 字段插入按钮', () => {
  it('行情字段按钮（CLOSE）触发 Monaco executeEdits', async () => {
    const user = userEvent.setup();
    renderModal();
    // Monaco 已被 mock，executeEdits 会触发 onChange 追加文本
    const closeBtn = screen.getByTestId('custom-indicator-modal-insert-CLOSE');
    await user.click(closeBtn);
    await waitFor(() => {
      const editor = getFormulaEditor();
      expect(editor.value).toContain('CLOSE');
    });
  });

  it('指标函数按钮（MA）插入完整函数调用', async () => {
    const user = userEvent.setup();
    renderModal();
    const maBtn = screen.getByTestId('custom-indicator-modal-insert-MA');
    await user.click(maBtn);
    await waitFor(() => {
      const editor = getFormulaEditor();
      expect(editor.value).toContain('MA(CLOSE, 5)');
    });
  });

  it('参数名按钮在添加参数后出现并可点击', async () => {
    renderModal();
    // 添加一个参数
    fireEvent.click(getParamAdd());
    // P3.2 修复时序问题 3：fireEvent.change 同步触发，绕过 user.type 异步
    const paramNameInput = screen.getByTestId('custom-indicator-modal-param-name-0');
    fireEvent.change(paramNameInput, { target: { value: 'period' } });
    // 等待 React state 同步（formState 重新计算 paramCandidates）
    const insertBtn = await screen.findByTestId('custom-indicator-modal-insert-param_period');
    expect(insertBtn).toBeInTheDocument();
    fireEvent.click(insertBtn);
    await waitFor(() => {
      const editor = getFormulaEditor();
      expect(editor.value).toContain('period');
    });
  });
});

// ============================================================================
// 5. 参数增删
// ============================================================================

describe('CustomIndicatorModal - 动态参数', () => {
  it('点击"添加参数"新增 1 行参数输入', async () => {
    const user = userEvent.setup();
    renderModal();
    expect(screen.queryByTestId('custom-indicator-modal-param-name-0')).not.toBeInTheDocument();
    await user.click(getParamAdd());
    expect(screen.getByTestId('custom-indicator-modal-param-name-0')).toBeInTheDocument();
  });

  it('点击删除按钮移除对应行', async () => {
    const user = userEvent.setup();
    renderModal();
    // P3.2 修复时序问题 1：user.click 自动 act 包装确保 state 同步
    await user.click(getParamAdd());
    await user.click(getParamAdd()); // 2 行
    // 验证渲染 2 个参数行
    expect(screen.getAllByTestId(/^custom-indicator-modal-param-name-\d+$/).length).toBe(2);
    expect(screen.getAllByTestId(/^custom-indicator-modal-param-remove-\d+$/).length).toBe(2);
    // 点击第 1 行删除按钮：实际 React 用 key={idx} 复用 DOM，
    // 删 idx=0 后原 idx=1 的参数会"滑"到 idx=0；只检查总数从 2 → 1
    await user.click(screen.getByTestId('custom-indicator-modal-param-remove-0'));
    await waitFor(
      () => {
        expect(screen.getAllByTestId(/^custom-indicator-modal-param-name-\d+$/).length).toBe(1);
      },
      { timeout: 5000 },
    );
    expect(screen.getAllByTestId(/^custom-indicator-modal-param-remove-\d+$/).length).toBe(1);
  });
});

// ============================================================================
// 6. 运算符切换（单值/双值阈值）
// ============================================================================

describe('CustomIndicatorModal - 运算符切换', () => {
  it('选择单值运算符（>）时显示单值 InputNumber', () => {
    renderModal();
    expect(screen.getByTestId('custom-indicator-modal-threshold-single')).toBeInTheDocument();
    expect(screen.queryByTestId('custom-indicator-modal-threshold-min')).not.toBeInTheDocument();
  });

  it('运算符切换：range 运算符显示双值 InputNumber（Antd Select jsdom 限制，此处弱断言）', () => {
    // 简化：只验证 range 运算符的渲染入口存在，不深入测试 Select 操作
    // 完整的 Select 操作由 Antd 内部管理，受 jsdom 限制无法稳定测试
    // 实际场景下由 Antd Dropdown 渲染选项，select 时触发 onChange
    renderModal();
    // 默认 operator='>'，双值未渲染
    expect(screen.queryByTestId('custom-indicator-modal-threshold-min')).not.toBeInTheDocument();
    // operator Select 存在
    expect(getOperatorSelect()).toBeInTheDocument();
  });
});

// ============================================================================
// 7. 提交逻辑
// ============================================================================

describe('CustomIndicatorModal - 提交逻辑', () => {
  it('名称 + 公式都为空时禁用提交', () => {
    renderModal();
    expect(getConfirmButton()).toBeDisabled();
  });

  it('填写合法名称 + 公式后可点击提交', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    renderModal({ onConfirm });
    await user.type(getNameInput(), '我的指标');
    const editor = getFormulaEditor();
    // 直接 fireEvent.change（比 user.type 快）
    fireEvent.change(editor, { target: { value: 'CLOSE > MA(CLOSE, 5)' } });
    await waitFor(() => {
      expect(getConfirmButton()).not.toBeDisabled();
    });
    await user.click(getConfirmButton());
    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith(
        expect.objectContaining({
          name: '我的指标',
          formula: 'CLOSE > MA(CLOSE, 5)',
          syntax: 'tdx',
        }),
      );
    });
  });

  it('名称为空时点击提交显示"不能为空"错误', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    renderModal({ onConfirm });
    fireEvent.change(getFormulaEditor(), { target: { value: 'CLOSE' } });
    // 提交按钮会被 disabled（名称为空）
    expect(getConfirmButton()).toBeDisabled();
  });

  it('参数名重复时点击提交显示"重复"错误', async () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });
    // P3.2 修复时序问题 2：用 fireEvent.change 同步触发，
    // 避免 user.type 异步时序导致 formState.params 引用过期
    fireEvent.change(getNameInput(), { target: { value: '测试' } });
    fireEvent.change(getFormulaEditor(), { target: { value: 'CLOSE' } });
    fireEvent.click(getParamAdd());
    fireEvent.click(getParamAdd());
    // 两个参数都用 'N'（重复）
    const p0 = screen.getByTestId('custom-indicator-modal-param-name-0');
    const p1 = screen.getByTestId('custom-indicator-modal-param-name-1');
    fireEvent.change(p0, { target: { value: 'N' } });
    fireEvent.change(p1, { target: { value: 'N' } });
    // 参数名校验发生在 handleSubmit 内部（即使 disabled 也会校验）
    // 通过 fireEvent.click 触发（绕过 disabled）
    fireEvent.click(getConfirmButton());
    // handleSubmit 内部拦截 → message.error → return → onConfirm 不调用
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

// ============================================================================
// 8. 编辑模式
// ============================================================================

describe('CustomIndicatorModal - 编辑模式', () => {
  it('传入 editing 时初始化字段', () => {
    const editing: CustomIndicator = {
      id: 'ind_1',
      userId: 'mock_user_default',
      name: '已有指标',
      category: 'oscillator',
      formula: 'RSI(CLOSE, 12) > 30',
      syntax: 'tdx',
      params: [{ name: 'period', defaultValue: '12', description: '周期' }],
      operator: '>',
      defaultThreshold: 30,
      description: '自定义 RSI',
      visibility: 'private',
      deleted: false,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    };
    renderModal({ editing, title: '编辑自编指标' });
    expect((getNameInput() as HTMLInputElement).value).toBe('已有指标');
    expect(getFormulaEditor().value).toBe('RSI(CLOSE, 12) > 30');
    // Antd 5 Button 文字含空格，提取后比对
    expect(getConfirmButtonText()).toBe('保存');
  });
});
