import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, render, screen } from '@testing-library/react';
import { ReactNode } from 'react';
import {
  screenerReducer,
  ScreenerProvider,
  useScreener,
  type ScreenerState,
} from '@/features/stock-picker/context/ScreenerContext';
import { FACTOR_CONFIG } from '@/features/stock-picker/config/indicatorConfig';

// ============ 工具：构造初始 state ============
const getInitialState = (): ScreenerState => ({
  selectedMarket: 'cn',
  selectedBoards: ['all'],
  stockRange: 'all',
  selectedMarketIndicators: [],
  marketIndicatorRanges: {},
  selectedFinancialIndicators: [],
  financialIndicatorRanges: {},
  selectedTechnicalIndicators: {},
  openTechnicalModal: null,
  factorWeights: FACTOR_CONFIG.reduce(
    (acc, f) => ({ ...acc, [f.id]: f.defaultWeight }),
    {} as Record<string, number>
  ),
  filterTree: null,
  nextConditionOp: 'AND',
  collapsedPanels: {
    range: true,
    market: true,
    financial: true,
    technical: true,
    factor: true,
    condition: true,
  },
});

// ============ Hook 工具：useScreener 但带 throw-on-missing 检测 ============
// 注意：必须是 React 组件（接收 props.children），不是普通函数
const Wrapper = ({ children }: { children: ReactNode }) => (
  <ScreenerProvider>{children}</ScreenerProvider>
);

describe('screenerReducer', () => {
  describe('TOGGLE_MARKET_INDICATOR（行情指标）', () => {
    it('添加指标时同时初始化 range = { min: "", max: "" }', () => {
      const state = getInitialState();
      const newState = screenerReducer(state, {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'market_cap',
      });
      expect(newState.selectedMarketIndicators).toContain('market_cap');
      expect(newState.marketIndicatorRanges['market_cap']).toEqual({ min: '', max: '' });
    });

    it('再次点击同 id 移除指标并删除对应 range', () => {
      let state = screenerReducer(getInitialState(), {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'pe_ttm',
      });
      state = screenerReducer(state, {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'pe_ttm',
      });
      expect(state.selectedMarketIndicators).not.toContain('pe_ttm');
      expect(state.marketIndicatorRanges['pe_ttm']).toBeUndefined();
    });

    it('已存在 range 时保留旧值（不重置）', () => {
      let state = screenerReducer(getInitialState(), {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'turnover',
      });
      // 用户先设置 range
      state = screenerReducer(state, {
        type: 'SET_MARKET_INDICATOR_RANGE',
        payload: { indicatorId: 'turnover', range: { min: '2', max: '10' } },
      });
      // 移除指标（应清空 range）
      state = screenerReducer(state, {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'turnover',
      });
      // 重新添加（应初始化为空 range，不是旧值）
      state = screenerReducer(state, {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'turnover',
      });
      expect(state.marketIndicatorRanges['turnover']).toEqual({ min: '', max: '' });
    });
  });

  describe('SET_MARKET_INDICATOR_RANGE', () => {
    it('更新范围', () => {
      let state = screenerReducer(getInitialState(), {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'turnover',
      });
      const newState = screenerReducer(state, {
        type: 'SET_MARKET_INDICATOR_RANGE',
        payload: { indicatorId: 'turnover', range: { min: '2', max: '10' } },
      });
      expect(newState.marketIndicatorRanges['turnover']).toEqual({ min: '2', max: '10' });
    });

    it('覆盖已有 range（不合并）', () => {
      let state = screenerReducer(getInitialState(), {
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'turnover',
      });
      state = screenerReducer(state, {
        type: 'SET_MARKET_INDICATOR_RANGE',
        payload: { indicatorId: 'turnover', range: { min: '1', max: '5' } },
      });
      const newState = screenerReducer(state, {
        type: 'SET_MARKET_INDICATOR_RANGE',
        payload: { indicatorId: 'turnover', range: { min: '3', max: '' } },
      });
      expect(newState.marketIndicatorRanges['turnover']).toEqual({ min: '3', max: '' });
    });
  });

  describe('SET_MARKET（市场切换清空行为）', () => {
    it('从 cn 切换到 cn：selectedBoards 重置为 ["all"]，所有指标清空', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'price' });
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'pe_static' });
      state = screenerReducer(state, {
        type: 'SET_MARKET_INDICATOR_RANGE',
        payload: { indicatorId: 'price', range: { min: '10', max: '50' } },
      });

      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'cn' });

      expect(after.selectedBoards).toEqual(['all']);
      expect(after.selectedMarketIndicators).toEqual([]);
      expect(after.marketIndicatorRanges).toEqual({});
      expect(after.selectedFinancialIndicators).toEqual([]);
      expect(after.financialIndicatorRanges).toEqual({});
      expect(after.selectedTechnicalIndicators).toEqual({});
    });

    it('切换到 hk（disabled 市场）：selectedBoards = []，所有指标清空', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'price' });
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });

      expect(after.selectedBoards).toEqual([]);
      expect(after.selectedMarketIndicators).toEqual([]);
    });

    it('切换到 us（disabled 市场）：selectedBoards = []，所有指标清空', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'volume' });
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'us' });

      expect(after.selectedBoards).toEqual([]);
      expect(after.selectedMarketIndicators).toEqual([]);
    });

    it('切换市场时保留 factorWeights', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'price' });
      const beforeWeights = { ...state.factorWeights };
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });
      expect(after.factorWeights).toEqual(beforeWeights);
    });
  });

  describe('TOGGLE_PANEL（折叠面板）', () => {
    it('切换后状态取反', () => {
      const state = getInitialState();
      const after = screenerReducer(state, { type: 'TOGGLE_PANEL', payload: 'market' });
      expect(after.collapsedPanels.market).toBe(!state.collapsedPanels.market);
    });

    it('只影响目标面板，不影响其他面板', () => {
      const state = getInitialState();
      const after = screenerReducer(state, { type: 'TOGGLE_PANEL', payload: 'market' });
      expect(after.collapsedPanels.financial).toBe(state.collapsedPanels.financial);
      expect(after.collapsedPanels.technical).toBe(state.collapsedPanels.technical);
    });
  });

  describe('RESET_ALL', () => {
    it('重置所有状态到 initialState', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'volume' });
      state = screenerReducer(state, {
        type: 'SET_MARKET_INDICATOR_RANGE',
        payload: { indicatorId: 'volume', range: { min: '100', max: '' } },
      });
      state = screenerReducer(state, { type: 'TOGGLE_PANEL', payload: 'market' });
      state = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });

      const after = screenerReducer(state, { type: 'RESET_ALL' });
      const initial = getInitialState();

      expect(after.selectedMarket).toBe(initial.selectedMarket);
      expect(after.selectedBoards).toEqual(initial.selectedBoards);
      expect(after.stockRange).toBe(initial.stockRange);
      expect(after.selectedMarketIndicators).toEqual([]);
      expect(after.marketIndicatorRanges).toEqual({});
      expect(after.collapsedPanels).toEqual(initial.collapsedPanels);
      expect(after.factorWeights).toEqual(initial.factorWeights);
    });
  });

  describe('Unknown action', () => {
    it('返回原 state（不抛错）', () => {
      const state = getInitialState();
      // 强制类型转换以模拟 unknown action
      const after = screenerReducer(
        state,
        // @ts-expect-error: 测试边界，故意传入未定义的 action
        { type: 'UNKNOWN_ACTION' }
      );
      expect(after).toBe(state);
    });
  });

  // ============ 条件构建器 filterTree 相关测试 ============
  describe('条件构建器 actions', () => {
    it('SET_NEXT_CONDITION_OP 改变 nextConditionOp', () => {
      const state = getInitialState();
      const after = screenerReducer(state, {
        type: 'SET_NEXT_CONDITION_OP',
        payload: 'OR',
      });
      expect(after.nextConditionOp).toBe('OR');
    });

    it('ADD_CONDITION 添加一个新 condition，op 来自 nextConditionOp', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'NOT' });
      const after = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'rsi_oversold', label: 'RSI超卖' },
      });
      expect(after.filterTree?.conditions).toHaveLength(1);
      expect(after.filterTree?.conditions[0].op).toBe('NOT');
      expect(after.filterTree?.conditions[0].fieldKey).toBe('rsi_oversold');
      expect(after.filterTree?.conditions[0].label).toBe('RSI超卖');
      expect(after.filterTree?.conditions[0].id).toMatch(/^cond_/);
    });

    it('ADD_CONDITION 追加：多次添加时新 condition 接在末尾', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'rsi_oversold', label: 'RSI超卖' },
      });
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'OR' });
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'volume_breakout', label: '放量突破' },
      });
      expect(state.filterTree?.conditions).toHaveLength(2);
      expect(state.filterTree?.conditions[0].fieldKey).toBe('rsi_oversold');
      expect(state.filterTree?.conditions[1].fieldKey).toBe('volume_breakout');
      expect(state.filterTree?.conditions[1].op).toBe('OR');
    });

    it('REMOVE_CONDITION 删除指定 id 的 condition', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'b', label: 'B' },
      });
      const targetId = state.filterTree!.conditions[0].id;
      const after = screenerReducer(state, {
        type: 'REMOVE_CONDITION',
        payload: targetId,
      });
      expect(after.filterTree?.conditions).toHaveLength(1);
      expect(after.filterTree?.conditions[0].fieldKey).toBe('b');
    });

    it('REMOVE_CONDITION 删完最后一个时 filterTree 回到 null', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      const targetId = state.filterTree!.conditions[0].id;
      const after = screenerReducer(state, {
        type: 'REMOVE_CONDITION',
        payload: targetId,
      });
      expect(after.filterTree).toBeNull();
    });

    it('UPDATE_CONDITION_OP 修改指定 id 的 op（不影响其他）', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'b', label: 'B' },
      });
      const targetId = state.filterTree!.conditions[0].id;
      const after = screenerReducer(state, {
        type: 'UPDATE_CONDITION_OP',
        payload: { id: targetId, op: 'OR' },
      });
      expect(after.filterTree?.conditions[0].op).toBe('OR');
      expect(after.filterTree?.conditions[1].op).toBe('AND'); // 不变
    });

    it('CLEAR_CONDITIONS 清空 filterTree 并重置 nextConditionOp', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'OR' });
      const after = screenerReducer(state, { type: 'CLEAR_CONDITIONS' });
      expect(after.filterTree).toBeNull();
      expect(after.nextConditionOp).toBe('AND');
    });

    it('APPLY_PRESET 替换当前 conditions 为预设的 1 个或多个', () => {
      let state = getInitialState();
      // 先添加一个无关条件
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'old', label: 'OLD' },
      });
      // 应用"底部放量+MACD金叉"预设（2 个条件）
      const after = screenerReducer(state, {
        type: 'APPLY_PRESET',
        payload: [
          { op: 'AND', fieldKey: 'volume_breakout', label: '底部放量' },
          { op: 'AND', fieldKey: 'macd_golden_cross', label: 'MACD金叉' },
        ],
      });
      expect(after.filterTree?.conditions).toHaveLength(2);
      expect(after.filterTree?.conditions[0].fieldKey).toBe('volume_breakout');
      expect(after.filterTree?.conditions[1].fieldKey).toBe('macd_golden_cross');
    });

    it('SET_MARKET 联动清空 filterTree 和 nextConditionOp', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'OR' });
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });
      expect(after.filterTree).toBeNull();
      expect(after.nextConditionOp).toBe('AND');
    });
  });
});

// ============ Provider / Hook 集成测试 ============
describe('ScreenerProvider / useScreener', () => {
  it('在 Provider 外调用 useScreener 抛出明确错误', () => {
    // 抑制 React 的错误日志（抛错时控制台会显示）
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => {
      renderHook(() => useScreener());
    }).toThrow('useScreener must be used within a ScreenerProvider');

    consoleError.mockRestore();
  });

  it('在 Provider 内可正常获取 state 和 dispatch', () => {
    const { result } = renderHook(() => useScreener(), { wrapper: Wrapper });
    expect(result.current.state.selectedMarket).toBe('cn');
    expect(typeof result.current.dispatch).toBe('function');
  });

  it('dispatch TOGGLE_MARKET_INDICATOR 后 state 变更', () => {
    const { result } = renderHook(() => useScreener(), { wrapper: Wrapper });
    act(() => {
      result.current.dispatch({
        type: 'TOGGLE_MARKET_INDICATOR',
        payload: 'market_cap',
      });
    });
    expect(result.current.state.selectedMarketIndicators).toContain('market_cap');
    expect(result.current.state.marketIndicatorRanges['market_cap']).toEqual({
      min: '',
      max: '',
    });
  });
});
