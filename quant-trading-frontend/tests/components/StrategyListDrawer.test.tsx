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
      />
    );
    expect(screen.getByText('策略A')).toBeInTheDocument();
    expect(screen.getByText('策略B')).toBeInTheDocument();
    expect(screen.getByText('策略C')).toBeInTheDocument();
  });
});

// 需要 fireEvent 用于 blur 事件
import { fireEvent } from '@testing-library/react';
