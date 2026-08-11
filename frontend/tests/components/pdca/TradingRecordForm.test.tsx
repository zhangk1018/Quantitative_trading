/**
 * TradingRecordForm 组件测试
 *
 * 覆盖：
 * - 渲染表单弹窗（新增模式）显示标题和必填字段
 * - 关闭弹窗时调用 onClose
 * - 编辑模式预填数据
 * - 提交有效表单后调用 API 并触发 onSuccess
 * - 提交空表单时显示必填校验提示
 * - API 失败时显示错误提示
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';
import { http, HttpResponse } from 'msw';
import { server } from '../../mocks/server';
import { pdcaHandlers, resetMockData } from '../../mocks/pdcaHandlers';
import TradingRecordForm from '@/features/pdca/components/TradingRecordForm';
import type { TradingRecord } from '@/features/pdca/types';

// 设置全局超时（JSDOM + Antd 渲染较慢）
vi.setConfig({ testTimeout: 60000 });

// 包装 Antd App 上下文
const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <App>{children}</App>
);

const mockOnClose = vi.fn();
const mockOnSuccess = vi.fn();

describe('TradingRecordForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetMockData();
    server.use(...pdcaHandlers);
  });

  it('新增模式下渲染表单弹窗，包含标题和必填字段', async () => {
    render(
      <TradingRecordForm
        open={true}
        record={null}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText('新增交易记录')).toBeInTheDocument();
    expect(screen.getByText('股票代码')).toBeInTheDocument();
    expect(screen.getByText('入场日期')).toBeInTheDocument();
    expect(screen.getByText('入场价')).toBeInTheDocument();
    expect(screen.getByText('数量(股)')).toBeInTheDocument();
  });

  it('关闭弹窗时调用 onClose', async () => {
    const user = userEvent.setup();
    render(
      <TradingRecordForm
        open={true}
        record={null}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper: Wrapper },
    );

    await screen.findByText('新增交易记录');

    const closeBtns = screen.getAllByLabelText('Close');
    const closeBtn = closeBtns[0];
    await user.click(closeBtn);
    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('编辑模式预填表单数据', async () => {
    const editRecord: TradingRecord = {
      id: 1, account_id: 1, pdca_cycle_id: 1, trading_plan_id: null,
      code: '600036', security_name: '招商银行', instrument_type: 'stock',
      long_short: 'long', order_type: 'limit',
      entry_date: '2026-08-01', exit_date: '2026-08-05',
      entry_price: 35.20, exit_price: 36.50, quantity: 1000,
      commission_entry: 5.0, commission_exit: 5.0, slip_point: 0.01,
      channel_height: null, gross_profit: 1300.00,
      entry_score: 85, exit_score: 80, trade_score: 82.5,
      trade_grade: 'A', trigger_source: 'system_plan',
      actual_stop_loss: null, exit_reason: 'take_profit',
      settlement_currency: 'CNY',
      created_at: '2026-08-01T09:30:00Z', updated_at: '2026-08-05T15:00:00Z',
    };

    render(
      <TradingRecordForm
        open={true}
        record={editRecord}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper: Wrapper },
    );

    expect(await screen.findByText('编辑交易记录')).toBeInTheDocument();
    const codeInput = screen.getByDisplayValue('600036');
    expect(codeInput).toBeInTheDocument();
  });

  it('提交有效表单后调用 API 并触发 onSuccess', async () => {
    const user = userEvent.setup();
    render(
      <TradingRecordForm
        open={true}
        record={null}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper: Wrapper },
    );

    await screen.findByText('新增交易记录');

    // 使用 user.type 填写表单（AutoComplete 和 DatePicker 需真实事件触发）
    const codeInput = screen.getByLabelText('股票代码');
    await user.type(codeInput, '600036');

    const dateInputs = document.querySelectorAll<HTMLInputElement>('.ant-picker input');
    await user.type(dateInputs[0], '2026-08-10');

    const priceInput = screen.getByRole('spinbutton', { name: /入场价/i });
    await user.type(priceInput, '35.20');

    // 点击保存按钮（通过 Modal footer 中的 primary button）
    const saveBtn = document.querySelector<HTMLButtonElement>('.ant-btn-primary')!;
    await user.click(saveBtn);

    // 验证 onSuccess 在 API 成功后调用
    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalledTimes(1);
    });

    // 验证成功提示出现
    await screen.findByText('新增成功');
  });

  it('提交空表单时显示必填校验提示', async () => {
    const user = userEvent.setup();
    render(
      <TradingRecordForm
        open={true}
        record={null}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper: Wrapper },
    );

    await screen.findByText('新增交易记录');

    // 点击保存按钮
    const saveBtn = document.querySelector<HTMLButtonElement>('.ant-btn-primary')!;
    await user.click(saveBtn);

    // 验证必填校验提示出现
    await screen.findByText('请输入股票代码');
  });

  it('API 返回错误时显示错误提示', async () => {
    const user = userEvent.setup();
    // 重写 createRecord handler 返回 500 错误
    server.use(
      http.post('/api/pdca/records', () => {
        return HttpResponse.json(
          { code: 500, message: '服务器内部错误', data: null },
          { status: 500 },
        );
      }),
    );

    render(
      <TradingRecordForm
        open={true}
        record={null}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
      />,
      { wrapper: Wrapper },
    );

    await screen.findByText('新增交易记录');

    // 使用 user.type 填写表单
    const codeInput = screen.getByLabelText('股票代码');
    await user.type(codeInput, '600036');
    const dateInputs = document.querySelectorAll<HTMLInputElement>('.ant-picker input');
    await user.type(dateInputs[0], '2026-08-10');
    const priceInput = screen.getByRole('spinbutton', { name: /入场价/i });
    await user.type(priceInput, '35.20');

    // 点击保存
    const saveBtn = document.querySelector<HTMLButtonElement>('.ant-btn-primary')!;
    await user.click(saveBtn);

    // 验证 onSuccess 未被调用
    await waitFor(() => {
      expect(mockOnSuccess).not.toHaveBeenCalled();
    });

    // 验证错误提示出现（API 返回 500 时显示服务器内部错误）
    await screen.findByText('服务器内部错误');
  });
});