import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfigProvider } from 'antd';
import { CustomIndicatorModal } from '@/features/stock-picker/components/CustomIndicatorModal';
import * as storage from '@/features/stock-picker/utils/customIndicatorStorage';

vi.mock('@monaco-editor/react', () => ({
  __esModule: true,
  default: function MockEditor(props: any) {
    return <textarea data-testid="monaco-editor" value={props.value ?? ''} onChange={(e) => props.onChange?.(e.target.value)} readOnly={props.options?.readOnly} rows={4} />;
  },
  loader: { config: vi.fn() },
}));

describe('DEBUG2: 删除参数 — 详细时序', () => {
  it('debug2', async () => {
    const user = userEvent.setup();
    storage.clearAllCustomIndicators();
    render(
      <ConfigProvider>
        <CustomIndicatorModal title="测试" editing={null} onConfirm={vi.fn()} onCancel={vi.fn()} />
      </ConfigProvider>,
    );
    await user.click(screen.getByTestId('custom-indicator-modal-param-add'));
    await user.click(screen.getByTestId('custom-indicator-modal-param-add'));
    // 立即同步
    const inputs = screen.getAllByTestId(/^custom-indicator-modal-param-name-/);
    console.log('[debug2] inputs after add:', inputs.map((i: any) => i.getAttribute('data-testid')));
    
    // 同步 click
    const removeBtn = screen.getByTestId('custom-indicator-modal-param-remove-0');
    fireEvent.click(removeBtn);
    const inputs2 = screen.queryAllByTestId(/^custom-indicator-modal-param-name-/);
    console.log('[debug2] inputs IMMEDIATELY after remove click:', inputs2.map((i: any) => i.getAttribute('data-testid')));
    
    // 等一会
    await new Promise(r => setTimeout(r, 100));
    const inputs3 = screen.queryAllByTestId(/^custom-indicator-modal-param-name-/);
    console.log('[debug2] inputs after 100ms:', inputs3.map((i: any) => i.getAttribute('data-testid')));
  });
});
