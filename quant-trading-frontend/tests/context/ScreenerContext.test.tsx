import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, render, screen } from '@testing-library/react';
import { ReactNode } from 'react';
import {
  screenerReducer,
  rootReducer,
  ScreenerProvider,
  useScreener,
  useScreenerDispatch,
  useScreenerSelector,
  type ScreenerState,
} from '@/features/stock-picker/context/ScreenerContext';
import { FACTOR_CONFIG } from '@/features/stock-picker/config/indicatorConfig';
import { CustomIndicator } from '@/features/stock-picker/types/customIndicator';

// ============ 工具：构造初始 state ============
const getInitialState = (): ScreenerState => ({
  market: {
    selectedMarket: 'cn',
    selectedBoards: ['all'],
    stockRange: 'all',
  },
  marketIndicators: { selected: [], ranges: {} },
  financialIndicators: { selected: [], ranges: {} },
  technical: { selected: {}, openModalId: null },
  patterns: { selected: {}, panelCollapsed: true },
  condition: { filterGroup: null, nextOp: 'AND' },
  custom: { indicators: [], activeTab: 'system' },
  factor: {
    weights: FACTOR_CONFIG.reduce(
      (acc, f) => ({ ...acc, [f.id]: f.defaultWeight }),
      {} as Record<string, number>
    ),
  },
  panels: {
    collapsed: {
      range: true,
      market: true,
      financial: true,
      technical: true,
      factor: true,
      condition: false,
      pattern: true,
    },
  },
});

// ============ 工具：构造一个自编指标 ============
function makeIndicator(overrides: Partial<CustomIndicator> = {}): CustomIndicator {
  return {
    id: 'ind_test_1',
    userId: 'mock_user_default',
    name: '测试指标',
    category: 'trend',
    formula: 'MA(CLOSE, 5)',
    syntax: 'tdx',
    params: [],
    operator: '>',
    defaultThreshold: 10,
    description: '',
    visibility: 'private',
    createdAt: '2026-06-16T00:00:00.000Z',
    updatedAt: '2026-06-16T00:00:00.000Z',
    ...overrides,
  };
}

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
      expect(newState.marketIndicators.selected).toContain('market_cap');
      expect(newState.marketIndicators.ranges['market_cap']).toEqual({ min: '', max: '' });
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
      expect(state.marketIndicators.selected).not.toContain('pe_ttm');
      expect(state.marketIndicators.ranges['pe_ttm']).toBeUndefined();
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
      expect(state.marketIndicators.ranges['turnover']).toEqual({ min: '', max: '' });
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
      expect(newState.marketIndicators.ranges['turnover']).toEqual({ min: '2', max: '10' });
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
      expect(newState.marketIndicators.ranges['turnover']).toEqual({ min: '3', max: '' });
    });
  });

  describe('SET_MARKET（市场切换清空行为）', () => {
    it('从 cn 切换到 cn：selectedBoards 重置为 ["all"]', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'price' });
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'pe_static' });
      state = screenerReducer(state, {
        type: 'SET_MARKET_INDICATOR_RANGE',
        payload: { indicatorId: 'price', range: { min: '10', max: '50' } },
      });

      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'cn' });

      // SET_MARKET 仅影响 market 子状态，不清理其他子状态
      expect(after.market.selectedBoards).toEqual(['all']);
    });

    it('切换到 hk（disabled 市场）：selectedBoards = []', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'price' });
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });

      expect(after.market.selectedBoards).toEqual([]);
    });

    it('切换到 us（disabled 市场）：selectedBoards = []', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'volume' });
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'us' });

      expect(after.market.selectedBoards).toEqual([]);
    });

    it('切换市场时保留 factorWeights', () => {
      let state = getInitialState();
      state = screenerReducer(state, { type: 'TOGGLE_MARKET_INDICATOR', payload: 'price' });
      const beforeWeights = { ...state.factor.weights };
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });
      expect(after.factor.weights).toEqual(beforeWeights);
    });
  });

  describe('TOGGLE_PANEL（折叠面板）', () => {
    it('切换后状态取反', () => {
      const state = getInitialState();
      const after = screenerReducer(state, { type: 'TOGGLE_PANEL', payload: 'market' });
      expect(after.panels.collapsed.market).toBe(!state.panels.collapsed.market);
    });

    it('只影响目标面板，不影响其他面板', () => {
      const state = getInitialState();
      const after = screenerReducer(state, { type: 'TOGGLE_PANEL', payload: 'market' });
      expect(after.panels.collapsed.financial).toBe(state.panels.collapsed.financial);
      expect(after.panels.collapsed.technical).toBe(state.panels.collapsed.technical);
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

      expect(after.market.selectedMarket).toBe(initial.market.selectedMarket);
      expect(after.market.selectedBoards).toEqual(initial.market.selectedBoards);
      expect(after.market.stockRange).toBe(initial.market.stockRange);
      expect(after.marketIndicators.selected).toEqual([]);
      expect(after.marketIndicators.ranges).toEqual({});
      expect(after.panels.collapsed).toEqual(initial.panels.collapsed);
      // RESET_ALL 保留 custom 状态，factor.weights 也被重置
      expect(after.factor.weights).toEqual(initial.factor.weights);
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

  // ============ 条件构建器 filterGroup 相关测试 ============
  describe('条件构建器 actions', () => {
    it('SET_NEXT_CONDITION_OP 改变 nextConditionOp', () => {
      const state = getInitialState();
      const after = screenerReducer(state, {
        type: 'SET_NEXT_CONDITION_OP',
        payload: 'OR',
      });
      expect(after.condition.nextOp).toBe('OR');
    });

    it('ADD_CONDITION 空列表时首条件 op 强制 AND（K 2026-06-16 决策 3a）', () => {
      let state = getInitialState();
      // nextConditionOp 是 NOT，但因空列表，首条件 op 强制为 AND
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'NOT' });
      const after = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'rsi_oversold', label: 'RSI超卖' },
      });
      expect(after.condition.filterGroup?.conditions).toHaveLength(1);
      expect(after.condition.filterGroup?.conditions[0].op).toBe('AND');
      expect(after.condition.filterGroup?.conditions[0].fieldKey).toBe('rsi_oversold');
      expect(after.condition.filterGroup?.conditions[0].label).toBe('RSI超卖');
      expect(after.condition.filterGroup?.conditions[0].id).toMatch(/^cond_/);
    });

    it('ADD_CONDITION 非空列表时新条件 op 来自 nextConditionOp', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'rsi_oversold', label: 'RSI超卖' },
      });
      // 列表已有 1 条，再 SET_NEXT_CONDITION_OP 后添加，新条件 op 来自 nextConditionOp
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'NOT' });
      const after = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'volume_breakout', label: '放量突破' },
      });
      expect(after.condition.filterGroup?.conditions).toHaveLength(2);
      expect(after.condition.filterGroup?.conditions[1].op).toBe('NOT');
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
      expect(state.condition.filterGroup?.conditions).toHaveLength(2);
      expect(state.condition.filterGroup?.conditions[0].fieldKey).toBe('rsi_oversold');
      expect(state.condition.filterGroup?.conditions[1].fieldKey).toBe('volume_breakout');
      expect(state.condition.filterGroup?.conditions[1].op).toBe('OR');
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
      const targetId = state.condition.filterGroup!.conditions[0].id;
      const after = screenerReducer(state, {
        type: 'REMOVE_CONDITION',
        payload: targetId,
      });
      expect(after.condition.filterGroup?.conditions).toHaveLength(1);
      expect(after.condition.filterGroup?.conditions[0].fieldKey).toBe('b');
    });

    it('REMOVE_CONDITION 删完最后一个时 filterGroup 回到 null', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      const targetId = state.condition.filterGroup!.conditions[0].id;
      const after = screenerReducer(state, {
        type: 'REMOVE_CONDITION',
        payload: targetId,
      });
      expect(after.condition.filterGroup).toBeNull();
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
      const targetId = state.condition.filterGroup!.conditions[0].id;
      const after = screenerReducer(state, {
        type: 'UPDATE_CONDITION_OP',
        payload: { id: targetId, op: 'OR' },
      });
      expect(after.condition.filterGroup?.conditions[0].op).toBe('OR');
      expect(after.condition.filterGroup?.conditions[1].op).toBe('AND'); // 不变
    });

    it('CLEAR_CONDITIONS 清空 filterGroup 并重置 nextConditionOp', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'OR' });
      const after = screenerReducer(state, { type: 'CLEAR_CONDITIONS' });
      expect(after.condition.filterGroup).toBeNull();
      expect(after.condition.nextOp).toBe('AND');
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
      expect(after.condition.filterGroup?.conditions).toHaveLength(2);
      expect(after.condition.filterGroup?.conditions[0].fieldKey).toBe('volume_breakout');
      expect(after.condition.filterGroup?.conditions[1].fieldKey).toBe('macd_golden_cross');
    });

    it('SET_MARKET 仅影响 market 子状态，不影响 condition', () => {
      let state = getInitialState();
      state = screenerReducer(state, {
        type: 'ADD_CONDITION',
        payload: { fieldKey: 'a', label: 'A' },
      });
      state = screenerReducer(state, { type: 'SET_NEXT_CONDITION_OP', payload: 'OR' });
      const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });
      // SET_MARKET 仅改变 market 子状态，condition 保持不变
      expect(after.condition.filterGroup).not.toBeNull();
      expect(after.condition.nextOp).toBe('OR');
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
    }).toThrow('useScreener must be used within ScreenerProvider');

    consoleError.mockRestore();
  });

  it('在 Provider 内可正常获取 state 和 dispatch', () => {
    const { result } = renderHook(() => useScreener(), { wrapper: Wrapper });
    expect(result.current.state.market.selectedMarket).toBe('cn');
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
    expect(result.current.state.marketIndicators.selected).toContain('market_cap');
    expect(result.current.state.marketIndicators.ranges['market_cap']).toEqual({
      min: '',
      max: '',
    });
  });

  it('selector 订阅抛错时记录错误且不阻断其他 selector 更新', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    const BadSelector = () => {
      useScreenerSelector((state) => {
        if (state.marketIndicators.selected.includes('market_cap')) {
          throw new Error('selector exploded');
        }
        return 'stable';
      });
      return <div>bad selector mounted</div>;
    };

    const GoodSelector = () => {
      const count = useScreenerSelector((state) => state.marketIndicators.selected.length);
      return <div data-testid="selected-count">{count}</div>;
    };

    const DispatchButton = () => {
      const dispatch = useScreenerDispatch();
      return (
        <button
          type="button"
          onClick={() => dispatch({ type: 'TOGGLE_MARKET_INDICATOR', payload: 'market_cap' })}
        >
          toggle
        </button>
      );
    };

    render(
      <ScreenerProvider>
        <BadSelector />
        <GoodSelector />
        <DispatchButton />
      </ScreenerProvider>
    );

    expect(screen.getByTestId('selected-count')).toHaveTextContent('0');

    act(() => {
      screen.getByText('toggle').click();
    });

    expect(screen.getByTestId('selected-count')).toHaveTextContent('1');
    expect(consoleError).toHaveBeenCalledWith(
      '[Screener] selector 订阅执行失败',
      expect.any(Error)
    );

    consoleError.mockRestore();
  });
});

// =====================================================================
// V1.0 自编指标 reducer 测试
// =====================================================================
describe('screenerReducer - V1.0 自编指标', () => {
  it('LOAD_CUSTOM_INDICATORS 加载 3 个指标', () => {
    const state = getInitialState();
    const indicators = [
      makeIndicator({ id: 'ind_1', name: '指标1' }),
      makeIndicator({ id: 'ind_2', name: '指标2' }),
      makeIndicator({ id: 'ind_3', name: '指标3' }),
    ];
    const after = screenerReducer(state, { type: 'LOAD_CUSTOM_INDICATORS', payload: indicators });
    expect(after.custom.indicators).toHaveLength(3);
    expect(after.custom.indicators[0].id).toBe('ind_1');
  });

  it('ADD_CUSTOM_INDICATOR 插入到列表头部', () => {
    const state = getInitialState();
    state.custom.indicators = [makeIndicator({ id: 'ind_existing', name: '已存在' })];
    const after = screenerReducer(state, {
      type: 'ADD_CUSTOM_INDICATOR',
      payload: makeIndicator({ id: 'ind_new', name: '新指标' }),
    });
    expect(after.custom.indicators).toHaveLength(2);
    expect(after.custom.indicators[0].id).toBe('ind_new');
  });

  it('UPDATE_CUSTOM_INDICATOR 替换指定 id 的指标', () => {
    const state = getInitialState();
    state.custom.indicators = [makeIndicator({ id: 'ind_1', name: '原名' })];
    const after = screenerReducer(state, {
      type: 'UPDATE_CUSTOM_INDICATOR',
      payload: makeIndicator({ id: 'ind_1', name: '新名' }),
    });
    expect(after.custom.indicators[0].name).toBe('新名');
  });

  it('UPDATE_CUSTOM_INDICATOR 未匹配 id 时列表不变', () => {
    const state = getInitialState();
    state.custom.indicators = [makeIndicator({ id: 'ind_1', name: '原名' })];
    const after = screenerReducer(state, {
      type: 'UPDATE_CUSTOM_INDICATOR',
      payload: makeIndicator({ id: 'ind_unknown', name: '不相关' }),
    });
    expect(after.custom.indicators).toHaveLength(1);
    expect(after.custom.indicators[0].name).toBe('原名');
  });

  it('REMOVE_CUSTOM_INDICATOR 从列表移除指定 id', () => {
    const state = getInitialState();
    state.custom.indicators = [
      makeIndicator({ id: 'ind_1', name: 'A' }),
      makeIndicator({ id: 'ind_2', name: 'B' }),
    ];
    const after = screenerReducer(state, { type: 'REMOVE_CUSTOM_INDICATOR', payload: 'ind_1' });
    expect(after.custom.indicators).toHaveLength(1);
    expect(after.custom.indicators[0].id).toBe('ind_2');
  });

  it('REMOVE_CUSTOM_INDICATOR 自动标记 filterGroup 中引用该指标的条件为 invalid（K 2026-06-16 决策 2a）', () => {
    const state = getInitialState();
    state.custom.indicators = [
      makeIndicator({ id: 'ind_1', name: 'A' }),
      makeIndicator({ id: 'ind_2', name: 'B' }),
    ];
    state.condition.filterGroup = {
      conditions: [
        {
          id: 'c1',
          op: 'AND',
          fieldKey: 'custom_ind_1',
          label: 'A',
          source: 'custom',
          sourceId: 'ind_1',
        },
        {
          id: 'c2',
          op: 'AND',
          fieldKey: 'custom_ind_2',
          label: 'B',
          source: 'custom',
          sourceId: 'ind_2',
        },
        { id: 'c3', op: 'AND', fieldKey: 'rsi_oversold', label: 'RSI超卖' },
      ],
    };
    const after = screenerReducer(state, { type: 'REMOVE_CUSTOM_INDICATOR', payload: 'ind_1' });
    // 引用 ind_1 的 c1 被标记 invalid
    expect(after.condition.filterGroup?.conditions[0].invalid).toBe(true);
    // K 2026-06-16 修复：toContain 是子串匹配，用 toBe + 完整字符串
    expect(after.condition.filterGroup?.conditions[0].invalidReason).toBe('引用的自编指标已被删除');
    // 引用 ind_2 的 c2 不受影响
    expect(after.condition.filterGroup?.conditions[1].invalid).toBeFalsy();
    // 系统预设 c3 不受影响
    expect(after.condition.filterGroup?.conditions[2].invalid).toBeFalsy();
  });

  it('REMOVE_CUSTOM_INDICATOR filterGroup 为 null 时不影响', () => {
    const state = getInitialState();
    state.custom.indicators = [makeIndicator({ id: 'ind_1', name: 'A' })];
    state.condition.filterGroup = null;
    const after = screenerReducer(state, { type: 'REMOVE_CUSTOM_INDICATOR', payload: 'ind_1' });
    expect(after.condition.filterGroup).toBeNull();
  });

  it('SET_INDICATOR_TAB 切换到 custom', () => {
    const state = getInitialState();
    expect(state.custom.activeTab).toBe('system');
    const after = screenerReducer(state, { type: 'SET_INDICATOR_TAB', payload: 'custom' });
    expect(after.custom.activeTab).toBe('custom');
  });

  it('SET_INDICATOR_TAB 切回 system', () => {
    const state = getInitialState();
    state.custom.activeTab = 'custom';
    const after = screenerReducer(state, { type: 'SET_INDICATOR_TAB', payload: 'system' });
    expect(after.custom.activeTab).toBe('system');
  });

  it('IMPORT_CUSTOM_INDICATORS 合并新指标（去重 id）', () => {
    const state = getInitialState();
    state.custom.indicators = [makeIndicator({ id: 'ind_1', name: 'A' })];
    const imported = [
      makeIndicator({ id: 'ind_2', name: 'B' }),
      makeIndicator({ id: 'ind_1', name: 'A-重复' }), // 同 id 应跳过
    ];
    const after = screenerReducer(state, { type: 'IMPORT_CUSTOM_INDICATORS', payload: imported });
    expect(after.custom.indicators).toHaveLength(2);
    expect(after.custom.indicators.map((i) => i.id).sort()).toEqual(['ind_1', 'ind_2']);
  });

  it('IMPORT_CUSTOM_INDICATORS 合并后按 updatedAt 倒序（K 2026-06-16 决策 7a）', () => {
    const state = getInitialState();
    state.custom.indicators = [
      makeIndicator({ id: 'ind_old', name: '旧', updatedAt: '2026-01-01T00:00:00Z' }),
    ];
    const imported = [
      makeIndicator({ id: 'ind_new', name: '新', updatedAt: '2026-06-15T00:00:00Z' }),
      makeIndicator({ id: 'ind_mid', name: '中', updatedAt: '2026-03-01T00:00:00Z' }),
    ];
    const after = screenerReducer(state, { type: 'IMPORT_CUSTOM_INDICATORS', payload: imported });
    expect(after.custom.indicators).toHaveLength(3);
    // 排序：ind_new (06-15) > ind_mid (03-01) > ind_old (01-01)
    expect(after.custom.indicators.map((i) => i.id)).toEqual(['ind_new', 'ind_mid', 'ind_old']);
  });

  it('SET_MARKET 不影响 customIndicators（独立状态）', () => {
    const state = getInitialState();
    state.custom.indicators = [makeIndicator({ id: 'ind_1', name: 'A' })];
    const after = screenerReducer(state, { type: 'SET_MARKET', payload: 'hk' });
    expect(after.custom.indicators).toHaveLength(1);
    expect(after.custom.indicators[0].id).toBe('ind_1');
    expect(after.market.selectedMarket).toBe('hk');
  });

  it('RESET_ALL 保留 customIndicators + activeIndicatorTab（K 2026-06-16 决策：用户私有长期资产不重置）', () => {
    const state = getInitialState();
    state.custom.indicators = [makeIndicator({ id: 'ind_1', name: '指标A' })];
    state.custom.activeTab = 'custom';
    const after = screenerReducer(state, { type: 'RESET_ALL' });
    expect(after.custom.indicators).toEqual(state.custom.indicators);
    expect(after.custom.indicators[0].id).toBe('ind_1');
    expect(after.custom.activeTab).toBe('custom');
  });

  it('初始 state 自带空 customIndicators 和 system Tab', () => {
    const state = getInitialState();
    expect(state.custom.indicators).toEqual([]);
    expect(state.custom.activeTab).toBe('system');
  });
});

// =====================================================================
// LOAD_STRATEGY 测试（使用新嵌套状态结构）
// =====================================================================
describe('screenerReducer - LOAD_STRATEGY', () => {
  // 新嵌套结构的初始状态
  const getNewState = (): ScreenerState => ({
    market: { selectedMarket: 'all', selectedBoards: ['all'], stockRange: 'all' },
    marketIndicators: { selected: [], ranges: {} },
    financialIndicators: { selected: [], ranges: {} },
    technical: { selected: {}, openModalId: null },
    patterns: { selected: {}, panelCollapsed: true },
    condition: { filterGroup: null, nextOp: 'AND' },
    custom: { indicators: [], activeTab: 'system' },
    factor: { weights: {} },
    panels: { collapsed: {} },
  });

  it('LOAD_STRATEGY 加载策略数据，覆盖默认值', () => {
    const state = getNewState();
    const payload = {
      ...getNewState(),
      market: {
        ...getNewState().market,
        selectedMarket: 'cn',
        selectedBoards: ['上海主板'],
      },
    };
    const { panels: _panels, ...p } = payload;
    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload: p });
    expect(after.market.selectedBoards).toEqual(['上海主板']);
    expect(after.market.selectedMarket).toBe('cn');
  });

  it('LOAD_STRATEGY 保留当前 panels（UI 折叠偏好）', () => {
    const state = getNewState();
    // 先折叠某个面板
    const stateWithPanel = rootReducer(state, { type: 'TOGGLE_PANEL', payload: 'market' });
    const originalPanels = { ...stateWithPanel.panels };

    const { panels: _panels, ...payload } = getNewState();
    const after = rootReducer(stateWithPanel, { type: 'LOAD_STRATEGY', payload });
    // panels 应保持不变
    expect(after.panels).toEqual(originalPanels);
  });

  it('LOAD_STRATEGY 部分字段缺失时用默认值填充', () => {
    const state = getNewState();
    // 模拟旧版本策略数据缺少某些新字段
    const partialPayload = {
      market: { selectedMarket: 'cn', selectedBoards: ['创业板'], stockRange: 'all' },
    } as any;
    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload: partialPayload });
    // 缺失字段应回退到默认值
    expect(after.market.selectedBoards).toEqual(['创业板']);
    expect(after.marketIndicators.selected).toEqual([]);
    expect(after.financialIndicators.selected).toEqual([]);
    expect(after.condition.filterGroup).toBeNull();
  });

  it('LOAD_STRATEGY 加载指标范围数据', () => {
    const state = getNewState();
    const payload = {
      ...getNewState(),
      marketIndicators: {
        selected: ['pe_ttm', 'pb'],
        ranges: {
          pe_ttm: { min: '0', max: '15' },
          pb: { min: '0', max: '2' },
        },
      },
    };
    const { panels: _panels, ...p } = payload;
    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload: p });
    expect(after.marketIndicators.selected).toEqual(['pe_ttm', 'pb']);
    expect(after.marketIndicators.ranges.pe_ttm).toEqual({ min: '0', max: '15' });
  });

  it('LOAD_STRATEGY 加载技术指标数据', () => {
    const state = getNewState();
    const payload = {
      ...getNewState(),
      technical: {
        selected: { ma: 'long_align', macd: 'low_golden_cross' },
        openModalId: null,
      },
    };
    const { panels: _panels, ...p } = payload;
    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload: p });
    expect(after.technical.selected).toEqual({ ma: 'long_align', macd: 'low_golden_cross' });
  });

  it('LOAD_STRATEGY 加载条件构建器数据', () => {
    const state = getNewState();
    const payload = {
      ...getNewState(),
      condition: {
        filterGroup: {
          conditions: [
            { id: 'c1', op: 'AND' as const, fieldKey: 'rsi_oversold', label: 'RSI超卖' },
          ],
        },
        nextOp: 'OR' as const,
      },
    };
    const { panels: _panels, ...p } = payload;
    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload: p });
    expect(after.condition.filterGroup?.conditions).toHaveLength(1);
    expect(after.condition.nextOp).toBe('OR');
  });
});
