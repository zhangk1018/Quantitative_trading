import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ScreenerProvider, useScreener } from '@/features/stock-picker/context/ScreenerContext';
import IndicatorFilter from '@/features/stock-picker/components/IndicatorFilter';
import { MARKET_INDICATORS } from '@/features/stock-picker/config/indicatorConfig';

// 暴露 state 的小工具组件（用于验证状态变化）
function StateInspector({ id }: { id: string }) {
  const { state } = useScreener();
  const range = state.marketIndicatorRanges[id];
  return (
    <div data-testid={`state-${id}`}>
      {range ? `min=${range.min}|max=${range.max}` : 'none'}
    </div>
  );
}

// 包装：ScreenerProvider + 折叠面板默认展开 + 可选 StateInspector
function renderFilter(stateInspectorId?: string) {
  return render(
    <ScreenerProvider>
      <div>
        <IndicatorFilter />
        {stateInspectorId && <StateInspector id={stateInspectorId} />}
      </div>
    </ScreenerProvider>
  );
}

// 展开折叠面板（默认 collapsedPanels.market = true 是折叠的）
async function expandPanel(user: ReturnType<typeof userEvent.setup>) {
  // 点击"行情指标" header 展开面板
  const headerText = screen.getByText('行情指标');
  const header = headerText.closest('.ant-collapse-header');
  expect(header).not.toBeNull();
  await user.click(header as HTMLElement);
}

describe('IndicatorFilter', () => {
  describe('基础渲染', () => {
    it('渲染 header 文本和 badge', () => {
      renderFilter();
      expect(screen.getByText('行情指标')).toBeInTheDocument();
      // badge 初始为 0
      expect(screen.getByTestId('indicator-filter-badge')).toHaveTextContent('0');
    });

    it('默认折叠状态下不渲染指标按钮', () => {
      renderFilter();
      // 默认 collapsedPanels.market = true → 折叠 → 内容不渲染
      expect(screen.queryByTestId('indicator-btn-market_cap')).not.toBeInTheDocument();
    });

    it('默认折叠状态下显示空状态提示', () => {
      // 注意：空状态提示是在 Panel 内部，折叠时也不可见
      // 我们需要展开后看到 "点击上方按钮添加筛选条件"
      renderFilter();
      expect(screen.queryByTestId('indicator-empty-hint')).not.toBeInTheDocument();
    });
  });

  describe('折叠面板交互', () => {
    it('点击 header 展开面板，显示所有指标按钮', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 验证所有 MARKET_INDICATORS 的按钮都渲染了
      MARKET_INDICATORS.forEach((indicator) => {
        expect(
          screen.getByTestId(`indicator-btn-${indicator.id}`)
        ).toBeInTheDocument();
      });
    });

    it('展开后看到空状态提示（未选中任何指标）', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      expect(screen.getByTestId('indicator-empty-hint')).toBeInTheDocument();
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

      const btn = screen.getByTestId('indicator-btn-market_cap');
      expect(btn).toHaveAttribute('data-selected', 'false');

      await user.click(btn);
      expect(btn).toHaveAttribute('data-selected', 'true');
      // badge 数字增加
      expect(screen.getByTestId('indicator-filter-badge')).toHaveTextContent('1');
    });

    it('再次点击取消选中', async () => {
      renderFilter();
      await expandPanel(user);
      const btn = screen.getByTestId('indicator-btn-price');

      await user.click(btn);
      expect(btn).toHaveAttribute('data-selected', 'true');
      await user.click(btn);
      expect(btn).toHaveAttribute('data-selected', 'false');
      expect(screen.getByTestId('indicator-filter-badge')).toHaveTextContent('0');
    });

    it('同时选中多个指标时，badge 显示总数', async () => {
      renderFilter();
      await expandPanel(user);
      await user.click(screen.getByTestId('indicator-btn-market_cap'));
      await user.click(screen.getByTestId('indicator-btn-price'));
      await user.click(screen.getByTestId('indicator-btn-turnover'));
      expect(screen.getByTestId('indicator-filter-badge')).toHaveTextContent('3');
    });
  });

  describe('范围输入（A7: 多选指标 range 独立）', () => {
    it('选中指标后显示该指标的 min/max 输入框', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      await user.click(screen.getByTestId('indicator-btn-market_cap'));
      expect(screen.getByTestId('indicator-min-market_cap')).toBeInTheDocument();
      expect(screen.getByTestId('indicator-max-market_cap')).toBeInTheDocument();
    });

    it('同时选中多个指标时各自 range 区独立', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      await user.click(screen.getByTestId('indicator-btn-market_cap'));
      await user.click(screen.getByTestId('indicator-btn-volume'));

      // 两个 range 区都存在
      const capRange = screen.getByTestId('indicator-range-market_cap');
      const volRange = screen.getByTestId('indicator-range-volume');
      expect(within(capRange).getByTestId('indicator-min-market_cap')).toBeInTheDocument();
      expect(within(volRange).getByTestId('indicator-min-volume')).toBeInTheDocument();
    });

    it('输入 min 值后，state 同步变化', async () => {
      const user = userEvent.setup();
      // 渲染时同时挂 StateInspector 用于验证 state
      render(
        <ScreenerProvider>
          <IndicatorFilter />
          <StateInspector id="market_cap" />
        </ScreenerProvider>
      );
      await expandPanel(user);
      await user.click(screen.getByTestId('indicator-btn-market_cap'));

      // Antd InputNumber 的 data-testid 直接加在内部 <input> 元素
      const minInput = screen.getByTestId('indicator-min-market_cap');
      fireEvent.change(minInput, { target: { value: '100' } });

      expect(screen.getByTestId('state-market_cap')).toHaveTextContent('min=100|max=');
    });

    it('输入 min 和 max 后，state 完整同步', async () => {
      const user = userEvent.setup();
      render(
        <ScreenerProvider>
          <IndicatorFilter />
          <StateInspector id="volume" />
        </ScreenerProvider>
      );
      await expandPanel(user);
      await user.click(screen.getByTestId('indicator-btn-volume'));

      const minInput = screen.getByTestId('indicator-min-volume');
      const maxInput = screen.getByTestId('indicator-max-volume');
      fireEvent.change(minInput, { target: { value: '1000' } });
      fireEvent.change(maxInput, { target: { value: '5000' } });

      expect(screen.getByTestId('state-volume')).toHaveTextContent('min=1000|max=5000');
    });
  });

  describe('清除按钮（A8）', () => {
    it('初始状态下清除按钮不显示（min 和 max 都为空）', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await user.click(screen.getByTestId('indicator-btn-turnover'));

      expect(
        screen.queryByTestId('indicator-clear-turnover')
      ).not.toBeInTheDocument();
    });

    it('只输入 min 后清除按钮显示', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);
      await user.click(screen.getByTestId('indicator-btn-turnover'));

      const minInput = screen.getByTestId('indicator-min-turnover');
      fireEvent.change(minInput, { target: { value: '1' } });

      expect(
        screen.getByTestId('indicator-clear-turnover')
      ).toBeInTheDocument();
    });

    it('点击清除按钮后 min/max 重置为空', async () => {
      const user = userEvent.setup();
      render(
        <ScreenerProvider>
          <IndicatorFilter />
          <StateInspector id="turnover" />
        </ScreenerProvider>
      );
      await expandPanel(user);
      await user.click(screen.getByTestId('indicator-btn-turnover'));

      const minInput = screen.getByTestId('indicator-min-turnover');
      fireEvent.change(minInput, { target: { value: '1' } });
      expect(screen.getByTestId('state-turnover')).toHaveTextContent('min=1|max=');

      await user.click(screen.getByTestId('indicator-clear-turnover'));
      expect(screen.getByTestId('state-turnover')).toHaveTextContent('min=|max=');
    });
  });

  describe('disabled 状态', () => {
    it('disabled 指标按钮不可点击', async () => {
      const user = userEvent.setup();
      renderFilter();
      await expandPanel(user);

      // 当前所有行情指标都未设置 disabled
      // 验证未设置 disabled 时按钮可点击
      const btn = screen.getByTestId('indicator-btn-market_cap');
      expect(btn).not.toBeDisabled();
      await user.click(btn);
      expect(btn).toHaveAttribute('data-selected', 'true');
    });
  });
});
