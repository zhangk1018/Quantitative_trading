import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { SavedStrategy } from '@/features/stock-picker/hooks/useSavedStrategies';

const drawerRenderSpy = vi.fn();

const MockList = ({ dataSource = [], renderItem }: { dataSource?: unknown[]; renderItem: (item: unknown) => React.ReactNode }) => (
  <div>{dataSource.map(renderItem)}</div>
);
MockList.Item = ({ children }: { children: React.ReactNode }) => <div>{children}</div>;
MockList.Item.Meta = ({ title, description }: { title: React.ReactNode; description: React.ReactNode }) => (
  <div>
    <div>{title}</div>
    <div>{description}</div>
  </div>
);

vi.mock('antd', () => ({
  Drawer: ({ children }: { children: React.ReactNode }) => {
    drawerRenderSpy();
    return <div data-testid="mock-drawer">{children}</div>;
  },
  List: MockList,
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  Popconfirm: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Typography: {
    Text: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  },
  Empty: ({ description }: { description: string }) => <div>{description}</div>,
  message: {
    success: vi.fn(),
  },
}));

vi.mock('@ant-design/icons', () => ({
  DeleteOutlined: () => <span />,
  EditOutlined: () => <span />,
  ReloadOutlined: () => <span />,
}));

const makeStrategy = (): SavedStrategy => ({
  id: 's1',
  name: '测试策略',
  createdAt: '2026-07-12T00:00:00Z',
  updatedAt: '2026-07-12T00:00:00Z',
  version: 1,
  state: {
    market: { selectedMarket: 'cn', selectedBoards: [], stockRange: 'all' },
    marketIndicators: { selected: [], ranges: {} },
    financialIndicators: { selected: [], ranges: {} },
    technical: { selected: {}, openModalId: null },
    patterns: { selected: {}, panelCollapsed: true },
    condition: { filterGroup: null, nextOp: 'AND' },
    custom: { indicators: [], activeTab: 'system' },
    factor: { weights: {} },
  } as SavedStrategy['state'],
});

describe('StrategyListDrawer closed render', () => {
  it('visible=false 时不实例化 Antd Drawer，避免关闭状态触发 Drawer 内部 effect', async () => {
    drawerRenderSpy.mockClear();
    const { StrategyListDrawer } = await import('@/features/stock-picker/components/StrategyListDrawer');

    render(
      <StrategyListDrawer
        visible={false}
        strategies={[makeStrategy()]}
        onClose={vi.fn()}
        onLoad={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(drawerRenderSpy).not.toHaveBeenCalled();
    expect(screen.queryByTestId('mock-drawer')).not.toBeInTheDocument();
  });
});
