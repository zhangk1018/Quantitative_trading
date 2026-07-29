import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SaveStrategyModal } from '@/features/stock-picker/components/SaveStrategyModal';
import type { SavedStrategy } from '@/features/stock-picker/hooks/useSavedStrategies';

const makeStrategy = (overrides: Partial<SavedStrategy> = {}): SavedStrategy => ({
  id: 's1',
  name: '现有策略',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  version: 1,
  state: {} as any,
  ...overrides,
});

describe('SaveStrategyModal', () => {
  it('visible=true 时渲染弹窗', () => {
    render(
      <SaveStrategyModal
        visible={true}
        existingStrategies={[]}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    expect(screen.getByTestId('save-strategy-modal')).toBeInTheDocument();
    expect(screen.getByText('保存当前策略')).toBeInTheDocument();
  });

  it('visible=false 时不渲染弹窗', () => {
    render(
      <SaveStrategyModal
        visible={false}
        existingStrategies={[]}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    expect(screen.queryByTestId('save-strategy-modal')).not.toBeInTheDocument();
  });

  it('点击取消按钮调用 onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <SaveStrategyModal
        visible={true}
        existingStrategies={[]}
        onClose={onClose}
        onSave={vi.fn()}
      />
    );
    await user.click(screen.getByTestId('save-strategy-modal-cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('输入有效名称后点击保存调用 onSave', async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <SaveStrategyModal
        visible={true}
        existingStrategies={[]}
        onClose={vi.fn()}
        onSave={onSave}
      />
    );
    const input = screen.getByPlaceholderText(/请输入策略名称/);
    await user.type(input, '高ROE低PE');
    await user.click(screen.getByTestId('save-strategy-modal-ok'));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith('高ROE低PE');
    });
  });

  it('空名称不能保存（required 校验）', async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <SaveStrategyModal
        visible={true}
        existingStrategies={[]}
        onClose={vi.fn()}
        onSave={onSave}
      />
    );
    await user.click(screen.getByTestId('save-strategy-modal-ok'));

    await waitFor(() => {
      expect(screen.getByText('请输入策略名称')).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('重名时提示错误，不调用 onSave', async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(
      <SaveStrategyModal
        visible={true}
        existingStrategies={[makeStrategy({ name: '高ROE低PE' })]}
        onClose={vi.fn()}
        onSave={onSave}
      />
    );
    const input = screen.getByPlaceholderText(/请输入策略名称/);
    await user.type(input, '高ROE低PE');
    await user.click(screen.getByTestId('save-strategy-modal-ok'));

    await waitFor(() => {
      // Antd message.error 渲染在 DOM 中
      expect(screen.getByText('策略名称已存在，请使用其他名称')).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('reopen 时重置表单', async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <SaveStrategyModal
        visible={true}
        existingStrategies={[]}
        onClose={vi.fn()}
        onSave={onSave}
      />
    );
    const input = screen.getByPlaceholderText(/请输入策略名称/);
    await user.type(input, '测试');
    await user.click(screen.getByTestId('save-strategy-modal-ok'));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    // 关闭再重新打开（visible 从 true→false→true 触发 useEffect 重置）
    rerender(
      <SaveStrategyModal
        visible={false}
        existingStrategies={[]}
        onClose={vi.fn()}
        onSave={onSave}
      />
    );
    rerender(
      <SaveStrategyModal
        visible={true}
        existingStrategies={[]}
        onClose={vi.fn()}
        onSave={onSave}
      />
    );
    const newInput = screen.getByPlaceholderText(/请输入策略名称/);
    await waitFor(() => {
      expect(newInput).toHaveValue('');
    });
  });
});