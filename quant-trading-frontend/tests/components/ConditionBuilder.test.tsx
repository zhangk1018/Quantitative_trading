import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ScreenerProvider, useScreener } from '@/features/stock-picker/context/ScreenerContext';
import ConditionBuilder from '@/features/stock-picker/components/ConditionBuilder';
import { FILTER_PRESETS } from '@/features/stock-picker/types/filterTree';

// ============================================================================
// Helpers
// ============================================================================

/** 暴露 state 的小工具 */
function StateInspector({ testId = 'state-condition' }: { testId?: string }) {
  const { state } = useScreener();
  return (
    <div data-testid={testId}>{JSON.stringify({ filterTree: state.filterTree, nextConditionOp: state.nextConditionOp })}</div>
  );
}

function readState(): {
  filterTree: { conditions: { id: string; op: string; fieldKey: string; label: string }[] } | null;
  nextConditionOp: string;
} {
  const text = screen.getByTestId('state-condition').textContent || '{}';
  return JSON.parse(text);
}

function renderBuilder() {
  // K 2026-06-17 变更：ConditionBuilder 使用 useNavigate（跳转 /config），
  // 需要 MemoryRouter 提供 Router 上下文
  return render(
    <MemoryRouter>
      <ScreenerProvider>
        <div>
          <ConditionBuilder />
          <StateInspector />
        </div>
      </ScreenerProvider>
    </MemoryRouter>
  );
}

async function expandPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId('condition-builder-header'));
}

// ============================================================================
// Tests
// ============================================================================

describe('ConditionBuilder', () => {
  // --------------------------------------------------------------------------
  // 1. 基础渲染
  // --------------------------------------------------------------------------
  describe('基础渲染', () => {
    it('渲染 header、count 徽标、reset 按钮', () => {
      renderBuilder();
      expect(screen.getByTestId('condition-builder-header')).toHaveTextContent('条件构建器');
      expect(screen.getByTestId('condition-builder-count')).toHaveTextContent('0 个条件');
      expect(screen.getByTestId('condition-builder-reset')).toBeInTheDocument();
    });

    it('默认折叠时不显示 6 个预设按钮', () => {
      renderBuilder();
      FILTER_PRESETS.forEach((p) => {
        expect(screen.queryByTestId(`condition-preset-${p.fieldKey}`)).not.toBeInTheDocument();
      });
    });
  });

  // --------------------------------------------------------------------------
  // 2. 折叠面板
  // --------------------------------------------------------------------------
  describe('折叠面板', () => {
    it('点击 header 展开后，6 个预设按钮全部可见', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      FILTER_PRESETS.forEach((p) => {
        expect(screen.getByTestId(`condition-preset-${p.fieldKey}`)).toBeInTheDocument();
      });
      // 3 个关系按钮
      expect(screen.getByTestId('condition-op-and')).toBeInTheDocument();
      expect(screen.getByTestId('condition-op-or')).toBeInTheDocument();
      expect(screen.getByTestId('condition-op-not')).toBeInTheDocument();
      // 添加按钮
      expect(screen.getByTestId('condition-add')).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // 3. 预设应用
  // --------------------------------------------------------------------------
  describe('预设应用', () => {
    it('点击 RSI超卖 预设后，state 中添加 1 个 condition', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      await user.click(screen.getByTestId('condition-preset-rsi_oversold'));

      const { filterTree } = readState();
      expect(filterTree?.conditions).toHaveLength(1);
      expect(filterTree?.conditions[0].fieldKey).toBe('rsi_oversold');
      expect(screen.getByTestId('condition-builder-count')).toHaveTextContent('1 个条件');
    });

    it('点击"底部放量+MACD金叉"组合预设后，添加 2 个 AND 条件', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      await user.click(screen.getByTestId('condition-preset-bottom_volume_macd'));

      const { filterTree } = readState();
      expect(filterTree?.conditions).toHaveLength(2);
      expect(filterTree?.conditions[0].fieldKey).toBe('volume_breakout');
      expect(filterTree?.conditions[1].fieldKey).toBe('macd_golden_cross');
      expect(filterTree?.conditions[0].op).toBe('AND');
      expect(filterTree?.conditions[1].op).toBe('AND');
      expect(screen.getByTestId('condition-builder-count')).toHaveTextContent('2 个条件');
    });

    it('应用预设会替换已有 conditions（典型"应用"语义）', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      // 先应用 RSI超卖
      await user.click(screen.getByTestId('condition-preset-rsi_oversold'));
      expect(readState().filterTree?.conditions).toHaveLength(1);

      // 再应用 MACD金叉 → 替换为 1 个
      await user.click(screen.getByTestId('condition-preset-macd_golden_cross'));
      const { filterTree } = readState();
      expect(filterTree?.conditions).toHaveLength(1);
      expect(filterTree?.conditions[0].fieldKey).toBe('macd_golden_cross');
    });
  });

  // --------------------------------------------------------------------------
  // 4. 关系选择器
  // --------------------------------------------------------------------------
  describe('关系选择器（AND/OR/NOT）', () => {
    it('初始默认选中 AND', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);
      expect(readState().nextConditionOp).toBe('AND');
    });

    it('点击 OR 后 nextConditionOp 变为 OR', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      await user.click(screen.getByTestId('condition-op-or'));
      expect(readState().nextConditionOp).toBe('OR');
    });

    it('点击 NOT 后 nextConditionOp 变为 NOT', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      await user.click(screen.getByTestId('condition-op-not'));
      expect(readState().nextConditionOp).toBe('NOT');
    });

    it('关系选择仅影响下一个添加的条件，已添加的不变', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      // 默认 AND → 加 RSI超卖
      await user.click(screen.getByTestId('condition-add'));
      expect(readState().filterTree?.conditions[0].op).toBe('AND');

      // 切到 OR → 加自定义
      await user.click(screen.getByTestId('condition-op-or'));
      await user.click(screen.getByTestId('condition-add'));
      const { filterTree } = readState();
      expect(filterTree?.conditions).toHaveLength(2);
      // 第一个 op 不变（AND）
      expect(filterTree?.conditions[0].op).toBe('AND');
      // 第二个 op 是新选的 OR
      expect(filterTree?.conditions[1].op).toBe('OR');
    });
  });

  // --------------------------------------------------------------------------
  // 5. 添加 / 删除 / 循环切换 op
  // --------------------------------------------------------------------------
  describe('添加 / 删除 / 循环切换 op', () => {
    it('点击"+ 条件"添加一个自定义 condition，count=1', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      expect(screen.getByTestId('condition-empty')).toBeInTheDocument();

      await user.click(screen.getByTestId('condition-add'));
      const { filterTree } = readState();
      expect(filterTree?.conditions).toHaveLength(1);
      expect(screen.getByTestId('condition-builder-count')).toHaveTextContent('1 个条件');
      expect(screen.queryByTestId('condition-empty')).not.toBeInTheDocument();
    });

    it('点击删除按钮移除对应 condition', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      await user.click(screen.getByTestId('condition-add'));
      const { filterTree } = readState();
      const id = filterTree!.conditions[0].id;

      await user.click(screen.getByTestId(`condition-item-remove-${id}`));
      expect(readState().filterTree).toBeNull();
      expect(screen.getByTestId('condition-empty')).toBeInTheDocument();
    });

    it('点击 op 标签循环切换 AND → OR → NOT → AND', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      await user.click(screen.getByTestId('condition-add'));
      const { filterTree: f1 } = readState();
      const id = f1!.conditions[0].id;
      const opBtn = screen.getByTestId(`condition-item-op-${id}`);
      expect(opBtn).toHaveAttribute('data-op', 'AND');

      // 点一次 → OR
      await user.click(opBtn);
      expect(readState().filterTree?.conditions[0].op).toBe('OR');
      expect(screen.getByTestId(`condition-item-op-${id}`)).toHaveAttribute('data-op', 'OR');

      // 点二次 → NOT
      await user.click(screen.getByTestId(`condition-item-op-${id}`));
      expect(readState().filterTree?.conditions[0].op).toBe('NOT');

      // 点三次 → AND
      await user.click(screen.getByTestId(`condition-item-op-${id}`));
      expect(readState().filterTree?.conditions[0].op).toBe('AND');
    });
  });

  // --------------------------------------------------------------------------
  // 6. 重置
  // --------------------------------------------------------------------------
  describe('重置', () => {
    it('点击重置清空所有 conditions 并重置 nextConditionOp', async () => {
      const user = userEvent.setup();
      renderBuilder();
      await expandPanel(user);

      // 切到 OR，加 2 个
      await user.click(screen.getByTestId('condition-op-or'));
      await user.click(screen.getByTestId('condition-add'));
      await user.click(screen.getByTestId('condition-add'));
      expect(readState().filterTree?.conditions).toHaveLength(2);

      // 重置
      await user.click(screen.getByTestId('condition-builder-reset'));
      const { filterTree, nextConditionOp } = readState();
      expect(filterTree).toBeNull();
      expect(nextConditionOp).toBe('AND');
      expect(screen.getByTestId('condition-builder-count')).toHaveTextContent('0 个条件');
      expect(screen.getByTestId('condition-empty')).toBeInTheDocument();
    });
  });

  // --------------------------------------------------------------------------
  // 7. 市场切换联动
  // --------------------------------------------------------------------------
  describe('市场切换联动', () => {
    it('切换市场后 conditions 清空，nextConditionOp 回到 AND', async () => {
      const user = userEvent.setup();
      function MarketSwitcher() {
        const { dispatch } = useScreener();
        return (
          <button data-testid="switch-market" onClick={() => dispatch({ type: 'SET_MARKET', payload: 'hk' })}>
            switch
          </button>
        );
      }
      render(
        <MemoryRouter>
          <ScreenerProvider>
            <ConditionBuilder />
            <StateInspector />
            <MarketSwitcher />
          </ScreenerProvider>
        </MemoryRouter>
      );
      await expandPanel(user);

      // 加 2 个 + 切到 OR
      await user.click(screen.getByTestId('condition-op-or'));
      await user.click(screen.getByTestId('condition-add'));
      await user.click(screen.getByTestId('condition-add'));
      expect(readState().filterTree?.conditions).toHaveLength(2);

      // 切市场
      await user.click(screen.getByTestId('switch-market'));
      const { filterTree, nextConditionOp } = readState();
      expect(filterTree).toBeNull();
      expect(nextConditionOp).toBe('AND');
      expect(screen.getByTestId('condition-builder-count')).toHaveTextContent('0 个条件');
    });
  });
});
