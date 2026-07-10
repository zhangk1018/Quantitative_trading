import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ScreenerProvider, useScreener } from '@/features/stock-picker/context/ScreenerContext';
import TechnicalFilter from '@/features/stock-picker/components/TechnicalFilter';
import { TechnicalIndicatorModal } from '@/features/stock-picker/components/TechnicalIndicatorModal';
import {
  TECHNICAL_INDICATORS,
  type TechnicalIndicatorItem,
} from '@/features/stock-picker/config/indicatorConfig';

// ============================================================================
// Helpers（low 10: 提取公共函数）
// ============================================================================

/** 暴露 state 的小工具（使用 data-testid 避免污染组件结构） */
function StateInspector({ testId = 'state-technical' }: { testId?: string }) {
  const { state } = useScreener();
  return <div data-testid={testId}>{JSON.stringify(state.selectedTechnicalIndicators)}</div>;
}

/** 解析 state JSON（low 13: 严格 JSON 解析避免子串误匹配） */
function readState(): Record<string, string> {
  const text = screen.getByTestId('state-technical').textContent || '{}';
  return JSON.parse(text) as Record<string, string>;
}

function renderFilter() {
  return render(
    <ScreenerProvider>
      <div>
        <TechnicalFilter />
        <StateInspector />
      </div>
    </ScreenerProvider>
  );
}

async function expandPanel(user: ReturnType<typeof userEvent.setup>) {
  const header = screen.getByTestId('technical-filter-header');
  await user.click(header);
}

async function openModal(user: ReturnType<typeof userEvent.setup>, indicatorId: string) {
  await user.click(screen.getByTestId(`technical-btn-${indicatorId}`));
  await waitFor(() =>
    expect(screen.getByTestId(`technical-modal-${indicatorId}`)).toBeInTheDocument()
  );
}

async function closeModal(user: ReturnType<typeof userEvent.setup>, indicatorId: string) {
  await user.click(screen.getByTestId(`technical-modal-${indicatorId}-cancel`));
  await waitFor(() =>
    expect(screen.queryByTestId(`technical-modal-${indicatorId}`)).not.toBeInTheDocument()
  );
}

async function selectAndConfirm(
  user: ReturnType<typeof userEvent.setup>,
  indicatorId: string,
  optionValue: string
) {
  await user.click(screen.getByTestId(`technical-modal-${indicatorId}-option-${optionValue}`));
  await user.click(screen.getByTestId(`technical-modal-${indicatorId}-confirm`));
  await waitFor(() =>
    expect(screen.queryByTestId(`technical-modal-${indicatorId}`)).not.toBeInTheDocument()
  );
}

/** 切市场的工具组件（中 7） */
function MarketSwitcher({ target = 'hk' }: { target?: string }) {
  const { dispatch } = useScreener();
  return (
    <button data-testid="switch-market" onClick={() => dispatch({ type: 'SET_MARKET', payload: target })}>
      switch
    </button>
  );
}

// ============================================================================
// TechnicalFilter 组件测试
// ============================================================================

describe.skip('TechnicalFilter', () => {
  // 顶层 beforeEach：清理 disabled 残留
  // 备注：vitest 默认每个 test file 独立 module environment，
  // TECHNICAL_INDICATORS 在跨测试文件间不会污染；同文件内由 beforeEach 兜底
  beforeEach(() => {
    TECHNICAL_INDICATORS.forEach((ind) => {
      delete ind.disabled;
      delete (ind as TechnicalIndicatorItem & { disabledReason?: string }).disabledReason;
    });
  });

  // --------------------------------------------------------------------------
  // 1. 基础渲染
  // --------------------------------------------------------------------------
  describe('基础渲染', () => {
    it('渲染 header 文本和 badge（初始 0）', () => {
      renderFilter();
      expect(screen.getByText('技术指标')).toBeInTheDocument();
      expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('0');
    });

    it('默认折叠状态下不渲染指标按钮', () => {
      renderFilter();
      TECHNICAL_INDICATORS.forEach((ind) => {
        expect(screen.queryByTestId(`technical-btn-${ind.id}`)).not.toBeInTheDocument();
      });
    });
  });

  // --------------------------------------------------------------------------
  // 2. 折叠面板交互
  // --------------------------------------------------------------------------
  describe('折叠面板交互', () => {
    it('点击 header 展开后，4 个指标按钮（MA/MACD/BOLL/RSI）都可见', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      const expectedIds = ['ma', 'macd', 'boll', 'rsi'];
      expectedIds.forEach((id) => {
        expect(screen.getByTestId(`technical-btn-${id}`)).toBeInTheDocument();
      });
      expect(TECHNICAL_INDICATORS.map((i) => i.id)).toEqual(expectedIds);
    });
  });

  // --------------------------------------------------------------------------
  // 3. 指标按钮交互（点击打开弹窗）
  // --------------------------------------------------------------------------
  describe('指标按钮交互（点击打开弹窗）', () => {
    it.each([
      ['ma', 'MA·日K'],
      ['macd', 'MACD·日K'],
      ['boll', 'BOLL·日K'],
      ['rsi', 'RSI·日K'],
    ])('点击 %s 按钮打开 %s 弹窗', async (id, title) => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await openModal(user, id);
      expect(screen.getByText(title)).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // 4. 弹窗 → 选 Radio → 确定 → 写入 state
  // --------------------------------------------------------------------------
  describe('弹窗 → 选 Radio → 确定 → 写入 state', () => {
    it.each([
      ['ma', 'long_align', '多头排列'],
      ['macd', 'bottom_divergence', '底背离'],
      ['boll', 'break_upper', '升穿上轨'],
      ['rsi', 'low_golden_cross', '低位金叉'],
    ] as const)(
      '%s 弹窗选 %s（%s）并确定后，state 写入对应 option',
      async (id, option, _label) => {
        const user = userEvent.setup();
        renderFilter();
        await expandPanel(user);
        await openModal(user, id);
        await selectAndConfirm(user, id, option);

        await waitFor(() => {
          expect(readState()).toEqual({ [id]: option });
        });
        const btn = screen.getByTestId(`technical-btn-${id}`);
        expect(btn).toHaveAttribute('data-selected', 'true');
        expect(btn).toHaveAttribute('data-option', option);
        expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('1');
      }
    );
  });

  // --------------------------------------------------------------------------
  // 5. 弹窗取消场景
  // --------------------------------------------------------------------------
  describe('弹窗 → 取消场景', () => {
    it('选 Radio 后点取消，state 保持空', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await openModal(user, 'ma');
      await user.click(screen.getByTestId('technical-modal-ma-option-long_align'));
      await closeModal(user, 'ma');

      expect(readState()).toEqual({});
      const btn = screen.getByTestId('technical-btn-ma');
      expect(btn).toHaveAttribute('data-selected', 'false');
      expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('0');
    });

    // 中 5: 打开弹窗后直接取消（无任何选择），state 保持原值
    it('打开弹窗后直接取消（无任何选择），state 保持空', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await openModal(user, 'macd');
      // 不点任何 radio，直接点取消
      await closeModal(user, 'macd');

      expect(readState()).toEqual({});
      expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('0');
    });
  });

  // --------------------------------------------------------------------------
  // 6. 再次打开弹窗回显
  // --------------------------------------------------------------------------
  describe('再次打开弹窗回显', () => {
    it('已选 MA 后再次打开弹窗，Radio 回显已选项', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 第一次选择
      await openModal(user, 'ma');
      await selectAndConfirm(user, 'ma', 'long_align');

      // 第二次打开：验证回显
      await openModal(user, 'ma');
      const checkedRadio = document.querySelector<HTMLInputElement>(
        'input[type="radio"][value="long_align"]'
      );
      expect(checkedRadio?.checked).toBe(true);
    });

    // 高 4: BOLL 弹窗特有 UI 文本
    it('BOLL 已选 break_middle_up 后再次打开，显示"当前已选：升穿中轨"', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 选 BOLL 升穿中轨
      await openModal(user, 'boll');
      await selectAndConfirm(user, 'boll', 'break_middle_up');

      // 再次打开
      await openModal(user, 'boll');
      // 验证"当前已选"区域（精确定位"已选"容器避免和 Radio 标签冲突）
      const selectedArea = screen.getByTestId('technical-modal-boll-selected');
      expect(selectedArea).toHaveTextContent('当前已选');
      expect(selectedArea).toHaveTextContent('升穿中轨');
    });
  });

  // --------------------------------------------------------------------------
  // 7. 清除已选
  // --------------------------------------------------------------------------
  describe('清除已选项', () => {
    it('已选后再次打开点击"清除已选"，state 清空，弹窗保持打开', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      await openModal(user, 'ma');
      await selectAndConfirm(user, 'ma', 'long_align');

      await openModal(user, 'ma');
      await user.click(screen.getByTestId('technical-modal-ma-clear'));

      await waitFor(() => {
        expect(readState()).toEqual({});
      });
      // 弹窗应保留打开（清除只清 state，不关弹窗）
      expect(screen.getByTestId('technical-modal-ma')).toBeInTheDocument();
    });

    // 高 3: 清除已选后，确定按钮重新 disabled
    it('清除已选后，确定按钮重新 disabled', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 先选一个选项（使 confirm 启用）
      await openModal(user, 'macd');
      await user.click(screen.getByTestId('technical-modal-macd-option-top_divergence'));
      expect(screen.getByTestId('technical-modal-macd-confirm')).not.toBeDisabled();
      await selectAndConfirm(user, 'macd', 'top_divergence');

      // 再次打开：confirm 仍启用（tempOption 同步了 currentOption）
      await openModal(user, 'macd');
      expect(screen.getByTestId('technical-modal-macd-confirm')).not.toBeDisabled();

      // 清除已选
      await user.click(screen.getByTestId('technical-modal-macd-clear'));

      // confirm 重新 disabled
      await waitFor(() => {
        expect(screen.getByTestId('technical-modal-macd-confirm')).toBeDisabled();
      });
      expect(readState()).toEqual({});
    });
  });

  // --------------------------------------------------------------------------
  // 8. 更改已有选项（高 2）
  // --------------------------------------------------------------------------
  describe('更改已有选项', () => {
    it('MA 已选多头排列后改为空头排列，state 从 long_align 变为 short_align，badge 仍为 1', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 第一次：多头排列
      await openModal(user, 'ma');
      await selectAndConfirm(user, 'ma', 'long_align');
      expect(readState()).toEqual({ ma: 'long_align' });
      expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('1');

      // 第二次：改为空头排列
      await openModal(user, 'ma');
      await selectAndConfirm(user, 'ma', 'short_align');

      // state 变更
      expect(readState()).toEqual({ ma: 'short_align' });
      // 中 8: 同一指标重复选不同 option，badge 仍为 1
      expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('1');
      // data-option 同步更新
      const btn = screen.getByTestId('technical-btn-ma');
      expect(btn).toHaveAttribute('data-option', 'short_align');
    });
  });

  // --------------------------------------------------------------------------
  // 9. 多选同时存在
  // --------------------------------------------------------------------------
  describe('同时选中多个技术指标', () => {
    it('MA + RSI 各选一个，state 含 2 个条目，badge=2', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 选 MA
      await openModal(user, 'ma');
      await selectAndConfirm(user, 'ma', 'long_align');

      // 选 RSI
      await openModal(user, 'rsi');
      await selectAndConfirm(user, 'rsi', 'high_death_cross');

      expect(readState()).toEqual({ ma: 'long_align', rsi: 'high_death_cross' });
      expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('2');
    });
  });

  // --------------------------------------------------------------------------
  // 10. 切换市场
  // --------------------------------------------------------------------------
  describe('切换市场清空技术指标', () => {
    it('切换市场后已选技术指标全部清空', async () => {
      const user = userEvent.setup();
      render(
        <ScreenerProvider>
          <TechnicalFilter />
          <StateInspector />
          <MarketSwitcher />
        </ScreenerProvider>
      );
      await expandPanel(user);

      await openModal(user, 'ma');
      await selectAndConfirm(user, 'ma', 'long_align');
      expect(readState()).toEqual({ ma: 'long_align' });

      await user.click(screen.getByTestId('switch-market'));

      await waitFor(() => {
        expect(readState()).toEqual({});
        expect(screen.getByTestId('technical-filter-badge')).toHaveTextContent('0');
        const btn = screen.getByTestId('technical-btn-ma');
        expect(btn).toHaveAttribute('data-selected', 'false');
      });
    });

    // 中 7: 切换市场时关闭打开中的弹窗
    it('切换市场时关闭打开中的弹窗', async () => {
      const user = userEvent.setup();
      render(
        <ScreenerProvider>
          <TechnicalFilter />
          <StateInspector />
          <MarketSwitcher />
        </ScreenerProvider>
      );
      await expandPanel(user);

      // 打开弹窗
      await openModal(user, 'boll');
      expect(screen.getByTestId('technical-modal-boll')).toBeInTheDocument();

      // 切换市场
      await user.click(screen.getByTestId('switch-market'));

      // 弹窗应自动关闭
      await waitFor(() => {
        expect(screen.queryByTestId('technical-modal-boll')).not.toBeInTheDocument();
      });
      expect(readState()).toEqual({});
    });
  });

  // --------------------------------------------------------------------------
  // 11. 确定按钮启用/禁用（中 6）
  // --------------------------------------------------------------------------
  describe('确定按钮启用状态', () => {
    it('弹窗刚打开时"确定"按钮 disabled', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await openModal(user, 'ma');
      expect(screen.getByTestId('technical-modal-ma-confirm')).toBeDisabled();
    });

    it('点击 radio 后"确定"按钮变为 enabled', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await openModal(user, 'macd');
      expect(screen.getByTestId('technical-modal-macd-confirm')).toBeDisabled();

      // 点 radio 后启用
      await user.click(screen.getByTestId('technical-modal-macd-option-top_divergence'));
      expect(screen.getByTestId('technical-modal-macd-confirm')).not.toBeDisabled();
    });
  });

  // --------------------------------------------------------------------------
  // 12. 禁用指标（低 12）
  // --------------------------------------------------------------------------
  describe('禁用指标', () => {
    it('disabled 指标按钮不可点击，且不打开弹窗', async () => {
      const user = userEvent.setup();
      // 模拟 macd 被禁用
      const macd = TECHNICAL_INDICATORS.find((i) => i.id === 'macd')!;
      macd.disabled = true;
      macd.disabledReason = '后端 MACD 字段未提供';

      renderFilter();
      await expandPanel(user);

      const btn = screen.getByTestId('technical-btn-macd');
      expect(btn).toBeDisabled();

      // 点击尝试打开弹窗（Antd disabled 按钮 click 不会触发 onClick）
      await user.click(btn);
      // 弹窗不应出现
      expect(screen.queryByTestId('technical-modal-macd')).not.toBeInTheDocument();
    });
  });
});

// ============================================================================
// TechnicalIndicatorModal 单独测试
// ============================================================================

describe('TechnicalIndicatorModal', () => {
  beforeEach(() => {
    TECHNICAL_INDICATORS.forEach((ind) => {
      delete ind.disabled;
      delete (ind as TechnicalIndicatorItem & { disabledReason?: string }).disabledReason;
    });
  });

  // 高 1: 修正矛盾测试 - 真正测未传 onClear 的场景
  it('未传 onClear 时，已选 option 的弹窗不显示"清除已选"按钮', () => {
    const ma = TECHNICAL_INDICATORS.find((i) => i.id === 'ma')!;

    render(
      <TechnicalIndicatorModal
        title="MA·日K"
        indicator={ma}
        currentOption="long_align"
        onConfirm={() => {}}
        onCancel={() => {}}
        // 注意：未传 onClear
      />
    );

    // "清除已选"按钮不应存在
    expect(screen.queryByTestId('technical-modal-ma-clear')).not.toBeInTheDocument();
    // "当前已选"文案仍显示（因为有 currentOption），精确定位已选容器避免和 Radio 标签冲突
    const selectedArea = screen.getByTestId('technical-modal-ma-selected');
    expect(selectedArea).toHaveTextContent('当前已选');
    expect(selectedArea).toHaveTextContent('多头排列');
  });

  it('未传 onClear 时，无 currentOption 的弹窗不显示"当前已选"区域', () => {
    const ma = TECHNICAL_INDICATORS.find((i) => i.id === 'ma')!;

    render(
      <TechnicalIndicatorModal
        title="MA·日K"
        indicator={ma}
        currentOption={undefined}
        onConfirm={() => {}}
        onCancel={() => {}}
        // 未传 onClear
      />
    );

    // "当前已选"文案不存在
    expect(screen.queryByTestId('technical-modal-ma-selected')).not.toBeInTheDocument();
    // "清除已选"按钮也不存在
    expect(screen.queryByTestId('technical-modal-ma-clear')).not.toBeInTheDocument();
  });

  it('传 onClear 时，点击"清除已选"调用 onClear 回调', async () => {
    const user = userEvent.setup();
    const ma = TECHNICAL_INDICATORS.find((i) => i.id === 'ma')!;
    const onClear = vi.fn();

    render(
      <TechnicalIndicatorModal
        title="MA·日K"
        indicator={ma}
        currentOption="long_align"
        onConfirm={() => {}}
        onCancel={() => {}}
        onClear={onClear}
      />
    );

    await user.click(screen.getByTestId('technical-modal-ma-clear'));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
