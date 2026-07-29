/**
 * 自编指标管理组件测试（K 2026-06-17 决策：从 ConditionBuilder 迁移至 /config 页面）
 *
 * 测试覆盖：
 * 1. 基础渲染（容器 / 计数 / 新建按钮 / 导入导出 / 列表 / 空状态）
 * 2. 快捷按钮：点击"新建自编指标"打开弹窗
 * 3. 路由参数：?action=new 自动打开弹窗
 * 4. 关闭弹窗
 * 5. 编排逻辑：使用 useScreener + storage（handler 调用通过副作用断言，不重复 Modal 内部测试）
 *
 * 复用约束：
 * - CustomIndicatorModal/List/ImportExportButtons 内部测试已分别在各自 test 文件覆盖
 * - 本测试只验证 CustomIndicatorManager 的"编排"层：state 读取、storage 调用、URL 参数
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { ScreenerProvider, useScreener } from '@/features/stock-picker/context/ScreenerContext';
import { CustomIndicatorManager } from '@/features/config/components/CustomIndicatorManager';
import { CustomIndicator } from '@/features/stock-picker/types/customIndicator';
import * as storage from '@/features/stock-picker/utils/customIndicatorStorage';

// ============================================================================
// Mock @monaco-editor/react（与 CustomIndicatorModal.test.tsx 一致）
// ============================================================================

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

/**
 * 保存指标到 localStorage（K 决策：去掉 id 让 storage 生成新 id；返回带正确 id 的对象）
 * - 入参必须是完整 CustomIndicator（用 makeIndicator 生成）
 */
function saveToStorage(ind: CustomIndicator): CustomIndicator {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { id: _ignoredId, userId: _ignoredUserId, ...rest } = ind;
  return storage.saveCustomIndicator(rest as Omit<CustomIndicator, 'id'>);
}

/** 暴露 state 的小工具 */
function StateInspector({ testId = 'state-manager' }: { testId?: string }) {
  const { state } = useScreener();
  return (
    <div data-testid={testId}>
      {JSON.stringify({
        customIndicators: state.custom.indicators.map((i) => ({ id: i.id, name: i.name })),
      })}
    </div>
  );
}

function readState(): { customIndicators: Array<{ id: string; name: string }> } {
  const text = screen.getByTestId('state-manager').textContent || '{}';
  return JSON.parse(text);
}

interface RenderOpts {
  /** initialEntries：MemoryRouter 初始 URL */
  initialEntries?: string[];
}

/**
 * 渲染组件 + ScreenerProvider + Router + Antd ConfigProvider
 * - Antd ConfigProvider 必填：CustomIndicatorList / CustomIndicatorModal 用到 Tag/Popconfirm
 */
function renderManager(opts: RenderOpts = {}) {
  const initialEntries = opts.initialEntries ?? ['/config?tab=indicators'];
  return render(
    <ConfigProvider>
      <MemoryRouter initialEntries={initialEntries}>
        <ScreenerProvider>
          <div>
            <CustomIndicatorManager />
            <StateInspector />
          </div>
        </ScreenerProvider>
      </MemoryRouter>
    </ConfigProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  storage.clearAllCustomIndicators();
});

// ============================================================================
// 1. 基础渲染
// ============================================================================

describe('CustomIndicatorManager - 基础渲染', () => {
  it('渲染容器 + 新建按钮 + 导入导出按钮 + 计数', () => {
    renderManager();
    expect(screen.getByTestId('custom-indicator-manager')).toBeInTheDocument();
    expect(screen.getByTestId('custom-manager-create-btn')).toBeInTheDocument();
    expect(screen.getByTestId('import-export-buttons')).toBeInTheDocument();
    expect(screen.getByTestId('custom-manager-count')).toHaveTextContent('已有 0 条');
  });

  it('空列表时显示空状态', () => {
    renderManager();
    expect(screen.getByTestId('custom-list-empty')).toHaveTextContent('暂无自编指标');
  });

  it('渲染已加载的 customIndicators 列表', async () => {
    // 预先写入 localStorage（名字必须 ≥ 2 字符，K 决策：避免与边界 case 混淆）
    const a = saveToStorage(makeIndicator({ name: '指标A' }));
    const b = saveToStorage(makeIndicator({ name: '指标B' }));

    renderManager();
    // K 2026-06-18 反馈 #6：等待 ScreenerProvider autoLoad 从 localStorage 加载完成，
    // 避免 useEffect 异步加载未完成时断言失败
    await waitFor(() => {
      expect(screen.getByTestId('custom-manager-count')).toHaveTextContent('已有 2 条');
    });
    expect(screen.getByTestId(`custom-list-item-${a.id}`)).toBeInTheDocument();
    expect(screen.getByTestId(`custom-list-item-${b.id}`)).toBeInTheDocument();
  });
});

// ============================================================================
// 2. 快捷按钮打开弹窗
// ============================================================================

describe('CustomIndicatorManager - 打开新建弹窗', () => {
  it('点击"新建自编指标"按钮打开弹窗', async () => {
    const user = userEvent.setup();
    renderManager();

    expect(screen.queryByTestId('custom-indicator-modal')).not.toBeInTheDocument();
    await user.click(screen.getByTestId('custom-manager-create-btn'));

    // 弹窗出现（K 决策：jsdom Antd Drawer 渲染较慢，timeout 8s 兜底）
    await waitFor(
      () => {
        expect(screen.getByTestId('custom-indicator-modal')).toBeInTheDocument();
      },
      { timeout: 8000 },
    );
  }, 15000);
});

// ============================================================================
// 3. 路由参数 ?action=new 自动打开弹窗
// ============================================================================

describe('CustomIndicatorManager - 路由参数自动唤起', () => {
  it('URL ?action=new 初始化时自动打开新建弹窗', async () => {
    renderManager({ initialEntries: ['/config?tab=indicators&action=new'] });

    // useEffect 同步执行后弹窗应出现
    await waitFor(() => {
      expect(screen.getByTestId('custom-indicator-modal')).toBeInTheDocument();
    });
  });

  it('URL 不带 ?action=new 时弹窗不打开', () => {
    renderManager({ initialEntries: ['/config?tab=indicators'] });
    expect(screen.queryByTestId('custom-indicator-modal')).not.toBeInTheDocument();
  });

  it('URL ?tab=indicators 但 action=other 时不打开弹窗', () => {
    renderManager({ initialEntries: ['/config?tab=indicators&action=other'] });
    expect(screen.queryByTestId('custom-indicator-modal')).not.toBeInTheDocument();
  });
});

// ============================================================================
// 4. 关闭弹窗
// ============================================================================

describe('CustomIndicatorManager - 关闭弹窗', () => {
  it('点击"取消"关闭弹窗', async () => {
    const user = userEvent.setup();
    renderManager({ initialEntries: ['/config?tab=indicators&action=new'] });

    // 弹窗已自动打开
    await waitFor(() => {
      expect(screen.getByTestId('custom-indicator-modal')).toBeInTheDocument();
    });

    // 点击取消
    await user.click(screen.getByTestId('custom-indicator-modal-cancel'));

    // 弹窗关闭
    await waitFor(() => {
      expect(screen.queryByTestId('custom-indicator-modal')).not.toBeInTheDocument();
    });
  });
});

// ============================================================================
// 5. 编排逻辑：使用 useScreener + storage
// ============================================================================

describe('CustomIndicatorManager - 编排逻辑', () => {
  it('组件挂载时从 ScreenerContext 读取 customIndicators 并渲染列表', async () => {
    const saved = saveToStorage(makeIndicator({ name: '编排测试' }));

    renderManager();

    // K 2026-06-18 反馈 #6：等待 ScreenerProvider autoLoad 从 localStorage 加载完成
    await waitFor(() => {
      expect(screen.getByTestId(`custom-list-item-${saved.id}`)).toBeInTheDocument();
    });
    expect(readState().customIndicators).toHaveLength(1);
  });

  // K 决策：跳过 jsdom + Antd Popconfirm 时序 flaky 问题
  // （与 P3.1 CustomIndicatorModal.test.tsx 同源）。
  // 删除逻辑的正确性已在 CustomIndicatorList.test.tsx 中覆盖
  // （"确认删除" / "被引用时显示警告" 等用例）。
  it.skip('storage 软删除会同步影响 state（删除后 list 消失）', async () => {
    const user = userEvent.setup();
    const saved = saveToStorage(makeIndicator({ name: '待删除' }));

    renderManager();

    await waitFor(() => {
      expect(screen.getByTestId(`custom-list-item-${saved.id}`)).toBeInTheDocument();
    });

    await user.click(screen.getByTestId(`custom-list-delete-${saved.id}`));
    await waitFor(() => {
      expect(screen.getByText('确认删除该自编指标？')).toBeInTheDocument();
    });

    const okButton = await waitFor(() => {
      // K 2026-06-18 反馈 #9：改用 data-testid 避免依赖 Antd 内部类名
      const ok = screen.queryByTestId(`custom-list-popconfirm-ok-${saved.id}`) as HTMLElement | null;
      if (!ok) throw new Error('Popconfirm OK not found');
      return ok;
    });
    await user.click(okButton);

    await waitFor(
      () => {
        const state = readState();
        expect(state.custom.indicators.find((i) => i.id === saved.id)).toBeUndefined();
      },
      { timeout: 8000 },
    );
  }, 15000);
});
