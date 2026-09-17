import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrategyListDrawer } from '@/features/stock-picker/components/StrategyListDrawer';
import type { SavedStrategy } from '@/features/stock-picker/hooks/useSavedStrategies';

const makeStrategy = (overrides: Partial<SavedStrategy> = {}): SavedStrategy => ({
  id: 's1',
  name: '高ROE低PE',
  createdAt: '2026-06-15T10:00:00Z',
  updatedAt: '2026-06-15T10:00:00Z',
  version: 1,
  state: {
    market: { selectedMarket: 'cn', selectedBoards: ['上海主板'], stockRange: 'all' },
    marketIndicators: { selected: ['pe_ttm', 'pb'], ranges: {} },
    financialIndicators: { selected: [], ranges: {} },
    technical: { selected: {}, openModalId: null },
    patterns: { selected: {}, panelCollapsed: true },
    condition: { filterGroup: null, nextOp: 'AND' },
    custom: { indicators: [], activeTab: 'system' },
    factor: { weights: {} },
  } as any,
  ...overrides,
});

describe('StrategyListDrawer', () => {
  it('visible=true 时渲染抽屉', () => {
    render(
      <StrategyListDrawer
        visible={true}
        strategies={[]}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    expect(screen.getByTestId('strategy-list-drawer')).toBeInTheDocument();
    expect(screen.getByText('我的策略')).toBeInTheDocument();
  });

  it('visible=false 时不渲染', () => {
    render(
      <StrategyListDrawer
        visible={false}
        strategies={[]}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    expect(screen.queryByTestId('strategy-list-drawer')).not.toBeInTheDocument();
    expect(document.body.querySelector('.ant-drawer')).not.toBeInTheDocument();
  });

  it('空策略列表显示空状态', () => {
    render(
      <StrategyListDrawer
        visible={true}
        strategies={[]}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    expect(screen.getByText('暂无保存的策略')).toBeInTheDocument();
  });

  it('显示策略列表和摘要', () => {
    const strategies = [makeStrategy({ id: 's1', name: '高ROE低PE' })];
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    expect(screen.getByText('高ROE低PE')).toBeInTheDocument();
    // 摘要应包含市场+指标信息
    expect(screen.getByText(/上海主板/)).toBeInTheDocument();
    expect(screen.getByText(/2 个行情指标/)).toBeInTheDocument();
  });

  it('点击加载按钮调用 onLoad', async () => {
    const onLoad = vi.fn();
    const strategies = [makeStrategy({ id: 's1', name: '测试策略' })];
    const user = userEvent.setup();
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={onLoad}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId('strategy-load-s1'));
    expect(onLoad).toHaveBeenCalledWith(strategies[0]);
  });

  it('点击重命名按钮进入编辑模式', async () => {
    const strategies = [makeStrategy({ id: 's1', name: '原名称' })];
    const user = userEvent.setup();
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId('strategy-rename-s1'));
    // 编辑输入框出现
    const input = screen.getByTestId('strategy-rename-input-s1');
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue('原名称');
  });

  it('重命名输入框失焦时调用 onRename', async () => {
    const onRename = vi.fn();
    const strategies = [makeStrategy({ id: 's1', name: '原名称' })];
    const user = userEvent.setup();
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId('strategy-rename-s1'));
    const input = screen.getByTestId('strategy-rename-input-s1');
    await user.clear(input);
    await user.type(input, '新名称');
    // 失焦触发确认
    fireEvent.blur(input);

    await waitFor(() => {
      expect(onRename).toHaveBeenCalledWith('s1', '新名称');
    });
  });

  it('重命名输入框按 Enter 调用 onRename', async () => {
    const onRename = vi.fn();
    const strategies = [makeStrategy({ id: 's1', name: '原名称' })];
    const user = userEvent.setup();
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId('strategy-rename-s1'));
    const input = screen.getByTestId('strategy-rename-input-s1');
    await user.clear(input);
    await user.type(input, '新名称{Enter}');

    await waitFor(() => {
      expect(onRename).toHaveBeenCalledWith('s1', '新名称');
    });
  });

  it('重命名输入框按 Escape 取消编辑', async () => {
    const onRename = vi.fn();
    const strategies = [makeStrategy({ id: 's1', name: '原名称' })];
    const user = userEvent.setup();
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    await user.click(screen.getByTestId('strategy-rename-s1'));
    const input = screen.getByTestId('strategy-rename-input-s1');
    await user.clear(input);
    await user.type(input, '新名称{Escape}');

    await waitFor(() => {
      expect(screen.queryByTestId('strategy-rename-input-s1')).not.toBeInTheDocument();
    });
    expect(onRename).not.toHaveBeenCalled();
  });

  it('点击删除按钮弹出确认框，确认后调用 onDelete', async () => {
    const onDelete = vi.fn();
    const strategies = [makeStrategy({ id: 's1', name: '待删除策略' })];
    const user = userEvent.setup();
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={onDelete}
      />
    );
    await user.click(screen.getByTestId('strategy-delete-s1'));
    // Popconfirm 弹出
    await waitFor(() => {
      expect(screen.getByTestId('strategy-delete-ok-s1')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('strategy-delete-ok-s1'));

    await waitFor(() => {
      expect(onDelete).toHaveBeenCalledWith('s1');
    });
  });

  it('多个策略全部显示', () => {
    const strategies = [
      makeStrategy({ id: 's1', name: '策略A' }),
      makeStrategy({ id: 's2', name: '策略B' }),
      makeStrategy({ id: 's3', name: '策略C' }),
    ];
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );
    expect(screen.getByText('策略A')).toBeInTheDocument();
    expect(screen.getByText('策略B')).toBeInTheDocument();
    expect(screen.getByText('策略C')).toBeInTheDocument();
  });
});

// ============ 导出功能 ============
describe('StrategyListDrawer - 导出', () => {
  let createObjectURLSpy: ReturnType<typeof vi.spyOn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.spyOn>;
  let lastAnchor: HTMLAnchorElement | null = null;
  const originalAnchorClick = HTMLAnchorElement.prototype.click;

  beforeEach(() => {
    lastAnchor = null;
    createObjectURLSpy = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:mock-url' as unknown as URL);
    revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    // 拦截 <a> click 捕获下载锚点
    HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
      lastAnchor = this;
    };
  });

  afterEach(() => {
    createObjectURLSpy.mockRestore();
    revokeObjectURLSpy.mockRestore();
    HTMLAnchorElement.prototype.click = originalAnchorClick;
  });

  const renderDrawer = (strategies: SavedStrategy[]) =>
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
      />
    );

  it('导出按钮显示策略总数，无策略时禁用', () => {
    renderDrawer([makeStrategy({ id: 's1', name: '策略A' }), makeStrategy({ id: 's2', name: '策略B' })]);
    const btn = screen.getByTestId('strategy-export-btn');
    expect(btn).toHaveTextContent('导出(2)');
    expect(btn).not.toBeDisabled();
  });

  it('无策略时导出按钮禁用', () => {
    renderDrawer([]);
    expect(screen.getByTestId('strategy-export-btn')).toBeDisabled();
  });

  it('点击导出打开选择 Modal，默认全选全部策略', async () => {
    const user = userEvent.setup();
    renderDrawer([makeStrategy({ id: 's1', name: '策略A' }), makeStrategy({ id: 's2', name: '策略B' })]);
    await user.click(screen.getByTestId('strategy-export-btn'));

    const modal = await waitFor(() => screen.getByTestId('strategy-export-modal'));
    expect(modal).toBeInTheDocument();
    // 策略名同时出现在抽屉列表与 Modal 复选框中，用 getAllByText 断言
    expect(screen.getAllByText('策略A').length).toBeGreaterThan(0);
    expect(screen.getAllByText('策略B').length).toBeGreaterThan(0);
    // 默认全选 → 确认按钮文案含条数
    const confirm = screen.getByTestId('strategy-export-confirm');
    expect(confirm).toHaveTextContent('导出（2 条）');
  });

  it('确认导出触发下载（JSON 文件名含 screener-strategies）', async () => {
    const user = userEvent.setup();
    renderDrawer([makeStrategy({ id: 's1', name: '策略A' })]);
    await user.click(screen.getByTestId('strategy-export-btn'));
    await waitFor(() => screen.getByTestId('strategy-export-confirm'));
    await user.click(screen.getByTestId('strategy-export-confirm'));

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    expect(lastAnchor).not.toBeNull();
    expect(lastAnchor!.download).toContain('screener-strategies-');
    expect(lastAnchor!.download).toMatch(/\.json$/);
    // 导出内容含策略名称（jsdom Blob 无 text()，用 FileReader 读取）
    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    const exportedText = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(blob);
    });
    expect(exportedText).toContain('策略A');
    // Modal 关闭
    expect(screen.queryByTestId('strategy-export-modal')).not.toBeInTheDocument();
  });

  it('取消全选后确认按钮禁用', async () => {
    const user = userEvent.setup();
    renderDrawer([makeStrategy({ id: 's1', name: '策略A' }), makeStrategy({ id: 's2', name: '策略B' })]);
    await user.click(screen.getByTestId('strategy-export-btn'));
    await waitFor(() => screen.getByTestId('strategy-export-confirm'));

    // 点击"取消全选"（全选时复选框文案为"取消全选"）
    await user.click(screen.getByText('取消全选'));
    expect(screen.getByTestId('strategy-export-confirm')).toBeDisabled();
  });
});

// ============ 导入功能 ============
describe('StrategyListDrawer - 导入', () => {
  const renderDrawer = (strategies: SavedStrategy[], onImport = vi.fn()) =>
    render(
      <StrategyListDrawer
        visible={true}
        strategies={strategies}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onImport={onImport}
      />
    );

  const makeImportFile = (strategies: SavedStrategy[]) =>
    new File(
      [JSON.stringify({ version: 1, exportedAt: '2026-01-02T00:00:00Z', strategies })],
      'strategies.json',
      { type: 'application/json' },
    );

  it('导入按钮存在且可选择文件', () => {
    renderDrawer([]);
    expect(screen.getByTestId('strategy-import-btn')).toBeInTheDocument();
  });

  it('选择合法文件后弹出预览，确认导入调用 onImport', async () => {
    const onImport = vi.fn();
    const user = userEvent.setup();
    renderDrawer([makeStrategy({ id: 's1', name: '已有' })], onImport);

    const file = makeImportFile([makeStrategy({ id: 'x1', name: '导入策略' })]);
    await user.upload(screen.getByTestId('strategy-import-file-input'), file);

    // 预览弹窗出现且显示"将新增：1 条"
    await waitFor(() => {
      expect(screen.getByTestId('strategy-import-preview-modal')).toBeInTheDocument();
    });
    const previewModal = screen.getByTestId('strategy-import-preview-modal');
    expect(previewModal.textContent).toContain('将新增');
    expect(previewModal.textContent).toContain('1 条');

    // 确认导入
    await user.click(screen.getByText(/确认导入/));
    await waitFor(() => {
      expect(onImport).toHaveBeenCalledTimes(1);
    });
    const imported = onImport.mock.calls[0][0] as SavedStrategy[];
    expect(imported).toHaveLength(1);
    expect(imported[0].name).toBe('导入策略');
    // Modal 关闭
    expect(screen.queryByTestId('strategy-import-preview-modal')).not.toBeInTheDocument();
  });

  it('重名策略预览显示跳过，确认按钮禁用', async () => {
    const user = userEvent.setup();
    renderDrawer([makeStrategy({ id: 's1', name: '同名' })]);

    const file = makeImportFile([makeStrategy({ id: 'x1', name: '同名' })]);
    await user.upload(screen.getByTestId('strategy-import-file-input'), file);

    await waitFor(() => {
      expect(screen.getByTestId('strategy-import-preview-modal')).toBeInTheDocument();
    });
    const previewModal = screen.getByTestId('strategy-import-preview-modal');
    expect(previewModal.textContent).toContain('将跳过');
    expect(previewModal.textContent).toContain('1 条');
    // previewAdded === 0 → 确认按钮禁用
    expect(screen.getByText(/确认导入/).closest('button')).toBeDisabled();
  });

  it('选择非法 JSON 文件提示错误且不弹预览', async () => {
    const user = userEvent.setup();
    renderDrawer([]);

    const bad = new File(['not json'], 'bad.json', { type: 'application/json' });
    await user.upload(screen.getByTestId('strategy-import-file-input'), bad);

    await waitFor(() => {
      expect(document.body.textContent).toContain('JSON 解析失败');
    });
    expect(screen.queryByTestId('strategy-import-preview-modal')).not.toBeInTheDocument();
  });
});

// 需要 fireEvent 用于 blur 事件
import { fireEvent } from '@testing-library/react';
