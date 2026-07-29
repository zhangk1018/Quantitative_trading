import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ScreenerProvider, useScreener } from '@/features/stock-picker/context/ScreenerContext';
import FinancialFilter from '@/features/stock-picker/components/FinancialFilter';
import { FINANCIAL_INDICATORS } from '@/features/stock-picker/config/indicatorConfig';

// 暴露 state 的小工具组件（用于验证状态变化）
function StateInspector({ id }: { id: string }) {
  const { state } = useScreener();
  const range = state.financialIndicators.ranges[id];
  return (
    <div data-testid={`state-${id}`}>
      {range ? `min=${range.min}|max=${range.max}` : 'none'}
    </div>
  );
}

// 模拟"市场切换器"组件，用于触发 SET_MARKET 动作验证清空逻辑
function MarketSwitcher({ targetMarket = 'hk' }: { targetMarket?: string }) {
  const { dispatch } = useScreener();
  return (
    <button
      data-testid={`switch-to-${targetMarket}`}
      onClick={() => dispatch({ type: 'SET_MARKET', payload: targetMarket })}
    >
      switch
    </button>
  );
}

// 包装：ScreenerProvider + FinancialFilter + 可选 StateInspector / MarketSwitcher
function renderFilter(
  options: { stateInspectorId?: string; withMarketSwitcher?: boolean; targetMarket?: string } = {}
) {
  return render(
    <ScreenerProvider>
      <div>
        <FinancialFilter />
        {options.stateInspectorId && <StateInspector id={options.stateInspectorId} />}
        {options.withMarketSwitcher && <MarketSwitcher targetMarket={options.targetMarket} />}
      </div>
    </ScreenerProvider>
  );
}

// 展开折叠面板：使用 data-testid 定位，避免依赖 Antd 内部类名
async function expandPanel(user: ReturnType<typeof userEvent.setup>) {
  const header = screen.getByTestId('financial-filter-header');
  await user.click(header);
}

// 选中指标并等待 range 区出现（封装重复的 click + waitFor）
async function selectIndicatorAndWaitForRange(
  user: ReturnType<typeof userEvent.setup>,
  id: string
) {
  await user.click(screen.getByTestId(`financial-btn-${id}`));
  await waitFor(() => {
    expect(screen.getByTestId(`financial-range-${id}`)).toBeInTheDocument();
  });
}

describe('FinancialFilter', () => {
  // 顶层 beforeEach：清理 FINANCIAL_INDICATORS 数组元素的 disabled/disabledReason 残留
  // 防止 disabled describe 块的修改影响后续 describe
  beforeEach(() => {
    FINANCIAL_INDICATORS.forEach((ind) => {
      delete ind.disabled;
      delete ind.disabledReason;
    });
  });

  describe('基础渲染', () => {
    it('渲染 header 文本和 badge', () => {
      renderFilter();
      expect(screen.getByText('财务指标')).toBeInTheDocument();
      // badge 初始为 0
      expect(screen.getByTestId('financial-filter-badge')).toHaveTextContent('0');
    });

    it('默认折叠状态下不渲染指标按钮', () => {
      renderFilter();
      // 默认 collapsedPanels.financial = true → 折叠 → 内容不渲染
      expect(screen.queryByTestId('financial-btn-net_profit')).not.toBeInTheDocument();
      expect(screen.queryByTestId('financial-btn-revenue')).not.toBeInTheDocument();
      expect(screen.queryByTestId('financial-btn-roe')).not.toBeInTheDocument();
    });

    it('默认折叠状态下不显示空状态提示', () => {
      renderFilter();
      // 折叠时 Panel 内部内容不渲染
      expect(screen.queryByTestId('financial-empty-hint')).not.toBeInTheDocument();
    });
  });

  describe('折叠面板交互', () => {
    it('点击 header 展开面板，显示所有指标按钮', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 验证所有 FINANCIAL_INDICATORS 的按钮都渲染了
      FINANCIAL_INDICATORS.forEach((indicator) => {
        expect(
          screen.getByTestId(`financial-btn-${indicator.id}`)
        ).toBeInTheDocument();
      });
    });

    it('展开后看到空状态提示（未选中任何指标）', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      expect(screen.getByTestId('financial-empty-hint')).toBeInTheDocument();
    });
  });

  describe('指标按钮交互', () => {
    let user: ReturnType<typeof userEvent.setup>;
    beforeEach(() => {
      user = userEvent.setup();
    });

    it('点击按钮切换为选中（data-selected=true）', async () => {
      renderFilter();
      await expandPanel(user);

      const btn = screen.getByTestId('financial-btn-net_profit');
      expect(btn).toHaveAttribute('data-selected', 'false');

      await user.click(btn);
      // 用 waitFor 包裹，因为 badge 更新可能跨 tick
      await waitFor(() => {
        expect(btn).toHaveAttribute('data-selected', 'true');
        expect(screen.getByTestId('financial-filter-badge')).toHaveTextContent('1');
      });
    });

    it('再次点击取消选中', async () => {
      renderFilter();
      await expandPanel(user);
      const btn = screen.getByTestId('financial-btn-revenue');

      await user.click(btn);
      await waitFor(() => expect(btn).toHaveAttribute('data-selected', 'true'));
      await user.click(btn);
      await waitFor(() => {
        expect(btn).toHaveAttribute('data-selected', 'false');
        expect(screen.getByTestId('financial-filter-badge')).toHaveTextContent('0');
      });
    });

    it('同时选中多个指标时，badge 显示总数', async () => {
      renderFilter();
      await expandPanel(user);
      await user.click(screen.getByTestId('financial-btn-net_profit'));
      await user.click(screen.getByTestId('financial-btn-revenue'));
      await user.click(screen.getByTestId('financial-btn-roe'));
      await waitFor(() => {
        expect(screen.getByTestId('financial-filter-badge')).toHaveTextContent('3');
      });
    });

    it('选中指标后空状态提示消失，范围条件区显示', async () => {
      renderFilter();
      await expandPanel(user);
      expect(screen.getByTestId('financial-empty-hint')).toBeInTheDocument();

      await user.click(screen.getByTestId('financial-btn-net_profit'));

      await waitFor(() => {
        // 空状态提示应消失
        expect(screen.queryByTestId('financial-empty-hint')).not.toBeInTheDocument();
        // 范围条件标题应出现
        expect(screen.getByText('范围条件:')).toBeInTheDocument();
      });
    });
  });

  describe('范围条件区标签渲染', () => {
    it('选中指标后范围区显示 "指标名(单位)" 标签', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 净利润：元
      await selectIndicatorAndWaitForRange(user, 'net_profit');
      const profitRange = screen.getByTestId('financial-range-net_profit');
      expect(within(profitRange).getByText('净利润(元)')).toBeInTheDocument();

      // 营业收入：元
      await selectIndicatorAndWaitForRange(user, 'revenue');
      const revenueRange = screen.getByTestId('financial-range-revenue');
      expect(within(revenueRange).getByText('营业收入(元)')).toBeInTheDocument();

      // 净资产收益率：%
      await selectIndicatorAndWaitForRange(user, 'roe');
      const roeRange = screen.getByTestId('financial-range-roe');
      expect(within(roeRange).getByText('净资产收益率(%)')).toBeInTheDocument();
    });
  });

  describe('范围输入', () => {
    it('选中指标后显示该指标的 min/max 输入框', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      await selectIndicatorAndWaitForRange(user, 'net_profit');
      expect(screen.getByTestId('financial-min-net_profit')).toBeInTheDocument();
      expect(screen.getByTestId('financial-max-net_profit')).toBeInTheDocument();
    });

    it('同时选中多个指标时各自 range 区独立', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      await selectIndicatorAndWaitForRange(user, 'net_profit');
      await selectIndicatorAndWaitForRange(user, 'roe');

      // 两个 range 区都存在
      const profitRange = screen.getByTestId('financial-range-net_profit');
      const roeRange = screen.getByTestId('financial-range-roe');
      expect(within(profitRange).getByTestId('financial-min-net_profit')).toBeInTheDocument();
      expect(within(roeRange).getByTestId('financial-min-roe')).toBeInTheDocument();
    });

    it('输入 min 值后，state 同步变化', async () => {
      const user = userEvent.setup();
      renderFilter({ stateInspectorId: 'net_profit' });
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'net_profit');

      const minInput = screen.getByTestId('financial-min-net_profit');
      fireEvent.change(minInput, { target: { value: '1000' } });

      // waitFor 防止偶发竞态
      await waitFor(() => {
        expect(screen.getByTestId('state-net_profit')).toHaveTextContent('min=1000|max=');
      });
    });

    it('输入 min 和 max 后，state 完整同步', async () => {
      const user = userEvent.setup();
      renderFilter({ stateInspectorId: 'revenue' });
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'revenue');

      fireEvent.change(screen.getByTestId('financial-min-revenue'), { target: { value: '10000' } });
      fireEvent.change(screen.getByTestId('financial-max-revenue'), { target: { value: '500000' } });

      await waitFor(() => {
        expect(screen.getByTestId('state-revenue')).toHaveTextContent('min=10000|max=500000');
      });
    });

    it('取消选中指标后 range 状态被清空', async () => {
      const user = userEvent.setup();
      renderFilter({ stateInspectorId: 'roe' });
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'roe');
      fireEvent.change(screen.getByTestId('financial-min-roe'), { target: { value: '5' } });
      await waitFor(() => {
        expect(screen.getByTestId('state-roe')).toHaveTextContent('min=5|max=');
      });

      // 再次点击取消选中
      await user.click(screen.getByTestId('financial-btn-roe'));
      // 取消选中时 reducer 会清空该指标的 range
      await waitFor(() => {
        expect(screen.getByTestId('state-roe')).toHaveTextContent('none');
      });
    });

    it('支持负数输入（财务指标可负，如净利润亏损）', async () => {
      const user = userEvent.setup();
      renderFilter({ stateInspectorId: 'net_profit' });
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'net_profit');

      fireEvent.change(screen.getByTestId('financial-min-net_profit'), { target: { value: '-100000' } });
      fireEvent.change(screen.getByTestId('financial-max-net_profit'), { target: { value: '0' } });

      await waitFor(() => {
        expect(screen.getByTestId('state-net_profit')).toHaveTextContent('min=-100000|max=0');
      });
    });

    it('min > max 时不自动纠正，前端只负责传参不校验', async () => {
      const user = userEvent.setup();
      renderFilter({ stateInspectorId: 'roe' });
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'roe');

      // 用户故意把 min 设为 20，max 设为 5
      fireEvent.change(screen.getByTestId('financial-min-roe'), { target: { value: '20' } });
      fireEvent.change(screen.getByTestId('financial-max-roe'), { target: { value: '5' } });

      // 状态原样保存，组件不做自动纠正（业务后端会过滤 0 结果）
      await waitFor(() => {
        expect(screen.getByTestId('state-roe')).toHaveTextContent('min=20|max=5');
      });
    });
  });

  describe('清除按钮', () => {
    it('初始状态下清除按钮不显示（min 和 max 都为空）', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'net_profit');

      expect(screen.queryByTestId('financial-clear-net_profit')).not.toBeInTheDocument();
    });

    it('只输入 min 后清除按钮显示', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'revenue');

      fireEvent.change(screen.getByTestId('financial-min-revenue'), { target: { value: '1000' } });

      await waitFor(() => {
        expect(screen.getByTestId('financial-clear-revenue')).toBeInTheDocument();
      });
    });

    it('只输入 max 后清除按钮也显示', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'roe');

      fireEvent.change(screen.getByTestId('financial-max-roe'), { target: { value: '20' } });

      await waitFor(() => {
        expect(screen.getByTestId('financial-clear-roe')).toBeInTheDocument();
      });
    });

    it('同时输入 min 和 max 时清除按钮存在', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'net_profit');

      fireEvent.change(screen.getByTestId('financial-min-net_profit'), { target: { value: '100' } });
      fireEvent.change(screen.getByTestId('financial-max-net_profit'), { target: { value: '500' } });

      await waitFor(() => {
        expect(screen.getByTestId('financial-clear-net_profit')).toBeInTheDocument();
      });
    });

    it('点击清除按钮后 min/max 重置为空且按钮消失', async () => {
      const user = userEvent.setup();
      renderFilter({ stateInspectorId: 'net_profit' });
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'net_profit');

      fireEvent.change(screen.getByTestId('financial-min-net_profit'), { target: { value: '500' } });
      fireEvent.change(screen.getByTestId('financial-max-net_profit'), { target: { value: '1500' } });
      await waitFor(() => {
        expect(screen.getByTestId('financial-clear-net_profit')).toBeInTheDocument();
      });

      await user.click(screen.getByTestId('financial-clear-net_profit'));
      await waitFor(() => {
        expect(screen.getByTestId('state-net_profit')).toHaveTextContent('min=|max=');
        expect(screen.queryByTestId('financial-clear-net_profit')).not.toBeInTheDocument();
      });
    });

    it('清空输入到空字符串时清除按钮同步消失', async () => {
      const user = userEvent.setup();
      renderFilter({ stateInspectorId: 'revenue' });
      await expandPanel(user);
      await selectIndicatorAndWaitForRange(user, 'revenue');

      const minInput = screen.getByTestId('financial-min-revenue');
      fireEvent.change(minInput, { target: { value: '1000' } });
      await waitFor(() => {
        expect(screen.getByTestId('financial-clear-revenue')).toBeInTheDocument();
      });

      // 用户清空输入框到空字符串
      fireEvent.change(minInput, { target: { value: '' } });
      await waitFor(() => {
        expect(screen.getByTestId('state-revenue')).toHaveTextContent('min=|max=');
        expect(screen.queryByTestId('financial-clear-revenue')).not.toBeInTheDocument();
      });
    });
  });

  describe('disabled 状态', () => {
    // 直接修改 FINANCIAL_INDICATORS 数组元素属性来模拟 disabled 配置
    // 顶层 beforeEach 已清理 disabled 残留，这里无需重复
    function applyDisabled(id: string, reason: string) {
      const target = FINANCIAL_INDICATORS.find((i) => i.id === id);
      if (target) {
        target.disabled = true;
        target.disabledReason = reason;
      }
    }

    it('未设置 disabled 的指标按钮可点击', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 当前所有财务指标都未设置 disabled
      const btn = screen.getByTestId('financial-btn-net_profit');
      expect(btn).not.toBeDisabled();
      await user.click(btn);
      await waitFor(() => {
        expect(btn).toHaveAttribute('data-selected', 'true');
      });
    });

    it('disabled 指标按钮不可点击且点击不响应', async () => {
      applyDisabled('net_profit', '数据源无对应字段');
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      const btn = screen.getByTestId('financial-btn-net_profit');
      // disabled 按钮应处于禁用状态
      expect(btn).toBeDisabled();
      // 即使用 userEvent click 也不会改变 data-selected
      await user.click(btn);
      expect(btn).toHaveAttribute('data-selected', 'false');
      expect(screen.getByTestId('financial-filter-badge')).toHaveTextContent('0');
    });

    it('disabled 指标不显示 range 区（未点击时）', async () => {
      applyDisabled('net_profit', '数据源无对应字段');
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // net_profit disabled，点击无效
      await user.click(screen.getByTestId('financial-btn-net_profit'));
      expect(screen.queryByTestId('financial-range-net_profit')).not.toBeInTheDocument();
      expect(screen.queryByTestId('financial-min-net_profit')).not.toBeInTheDocument();

      // 选中 revenue，应该正常显示
      await user.click(screen.getByTestId('financial-btn-revenue'));
      await waitFor(() => {
        expect(screen.getByTestId('financial-range-revenue')).toBeInTheDocument();
      });
    });

    it('disabled 指标按钮在 hover 时通过 Tooltip 展示 disabledReason', async () => {
      applyDisabled('net_profit', '数据源无对应字段');
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 验证 disabled 按钮被 Tooltip 包裹（外层有 data-testid wrapper）
      const wrapper = screen.getByTestId('financial-btn-wrapper-net_profit');
      expect(wrapper).toBeInTheDocument();
      // 通过 Antd 的 Tooltip 在 hover 时渲染到 body 的 .ant-tooltip-inner
      const btn = screen.getByTestId('financial-btn-net_profit');
      await user.hover(btn);
      // Antd Tooltip 默认延迟 0~0.1s 出现，等待 DOM 中出现 tooltip 元素
      const tooltip = await screen.findByRole('tooltip', {}, { timeout: 2000 });
      expect(tooltip).toHaveTextContent('数据源无对应字段');
    });
  });

  describe('与 ScreenerContext 市场切换联动', () => {
    it('切换市场时保留已选财务指标和范围', async () => {
      const user = userEvent.setup();
      // 注入 MarketSwitcher 用于触发 SET_MARKET
      renderFilter({ stateInspectorId: 'net_profit', withMarketSwitcher: true, targetMarket: 'hk' });
      await expandPanel(user);

      // 1. 选中 net_profit 并设置 min
      await selectIndicatorAndWaitForRange(user, 'net_profit');
      fireEvent.change(screen.getByTestId('financial-min-net_profit'), { target: { value: '1000' } });
      await waitFor(() => {
        expect(screen.getByTestId('state-net_profit')).toHaveTextContent('min=1000|max=');
        expect(screen.getByTestId('financial-filter-badge')).toHaveTextContent('1');
      });

      // 2. 切换市场到 hk
      await user.click(screen.getByTestId('switch-to-hk'));

      // 3. 验证 state 被保留：financialIndicatorRanges 保持不变 + 徽标不变
      await waitFor(() => {
        expect(screen.getByTestId('state-net_profit')).toHaveTextContent('min=1000|max=');
        expect(screen.getByTestId('financial-filter-badge')).toHaveTextContent('1');
      });
      // 4. 验证 UI 也保留：之前选中的按钮仍为选中状态
      const btn = screen.getByTestId('financial-btn-net_profit');
      expect(btn).toHaveAttribute('data-selected', 'true');
    });

    it('切换市场时保留所有 3 个财务指标和它们各自的 range', async () => {
      const user = userEvent.setup();
      render(
        <ScreenerProvider>
          <FinancialFilter />
          <StateInspector id="net_profit" />
          <StateInspector id="revenue" />
          <StateInspector id="roe" />
          <MarketSwitcher targetMarket="us" />
        </ScreenerProvider>
      );
      await expandPanel(user);

      // 选中 3 个并各自设置 min
      await selectIndicatorAndWaitForRange(user, 'net_profit');
      fireEvent.change(screen.getByTestId('financial-min-net_profit'), { target: { value: '100' } });
      await selectIndicatorAndWaitForRange(user, 'revenue');
      fireEvent.change(screen.getByTestId('financial-min-revenue'), { target: { value: '200' } });
      await selectIndicatorAndWaitForRange(user, 'roe');
      fireEvent.change(screen.getByTestId('financial-min-roe'), { target: { value: '5' } });

      await waitFor(() => {
        expect(screen.getByTestId('state-net_profit')).toHaveTextContent('min=100');
        expect(screen.getByTestId('state-revenue')).toHaveTextContent('min=200');
        expect(screen.getByTestId('state-roe')).toHaveTextContent('min=5');
      });

      // 切换到 us 市场
      await user.click(screen.getByTestId('switch-to-us'));

      // 3 个 state 全部保留
      await waitFor(() => {
        expect(screen.getByTestId('state-net_profit')).toHaveTextContent('min=100');
        expect(screen.getByTestId('state-revenue')).toHaveTextContent('min=200');
        expect(screen.getByTestId('state-roe')).toHaveTextContent('min=5');
      });
    });
  });
});
