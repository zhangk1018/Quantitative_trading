/**
 * 策略加载后选股流程测试
 *
 * 验证：加载已保存策略后，筛选条件是否正确恢复并传递到后端请求参数
 * Bug 场景：加载策略后一个股票也选不对
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  rootReducer,
  type ScreenerState,
} from '@/features/stock-picker/context/ScreenerContext';
import { buildScreeningParams } from '@/features/stock-picker/utils/screener';
import { FACTOR_CONFIG } from '@/features/stock-picker/config/indicatorConfig';

// ============ 工具：构造初始 state ============
function getInitialState(): ScreenerState {
  return {
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
        {} as Record<string, number>,
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
  };
}

/**
 * 模拟 useScreenerData 中 stateRef 的格式
 * 生产代码中 useEffect 将 selector 值扁平化为 top-level filterGroup
 * （buildScreeningParams 接收 ScreenerFilterPayload 而非 ScreenerState）
 */
function toFilterPayload(s: ScreenerState): Parameters<typeof buildScreeningParams>[0] {
  return {
    selectedBoards: s.market.selectedBoards,
    stockRange: s.market.stockRange,
    marketIndicatorRanges: s.marketIndicators.ranges,
    financialIndicatorRanges: s.financialIndicators.ranges,
    selectedTechnicalIndicators: s.technical.selected,
    filterGroup: s.condition.filterGroup,
  };
}

describe('策略加载 → 选股参数构建', () => {
  let state: ScreenerState;

  beforeEach(() => {
    state = getInitialState();
  });

  it('加载含条件构建器条件的策略后，buildScreeningParams 应包含条件参数', () => {
    // 1. 先设置一些条件（模拟用户保存策略时的状态）
    const savedCondition = {
      filterGroup: {
        conditions: [
          {
            id: 'cond_1',
            op: 'AND' as const,
            fieldKey: 'rsi_oversold',
            label: 'RSI超卖',
          },
          {
            id: 'cond_2',
            op: 'AND' as const,
            fieldKey: 'volume_breakout',
            label: '放量突破',
          },
        ],
      },
      nextOp: 'AND' as const,
    };

    // 2. 模拟保存策略时的 state（serializeState 移除 panels）
    const savedStrategyState = {
      ...getInitialState(),
      condition: savedCondition,
    };
    const { panels: _panels, ...payload } = savedStrategyState;

    // 3. 加载策略
    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload });

    // 4. 验证条件被正确恢复
    expect(after.condition.filterGroup).not.toBeNull();
    expect(after.condition.filterGroup?.conditions).toHaveLength(2);
    expect(after.condition.filterGroup?.conditions[0].fieldKey).toBe('rsi_oversold');
    expect(after.condition.filterGroup?.conditions[1].fieldKey).toBe('volume_breakout');

    // 5. 验证 buildScreeningParams 包含条件参数（使用 stateRef 扁平格式）
    const params = buildScreeningParams(toFilterPayload(after), 'change_pct', false, 20, 0);
    expect(params['cond_rsi_oversold']).toBe('AND');
    expect(params['cond_volume_breakout']).toBe('AND');
  });

  it('加载含技术指标条件的策略后，buildScreeningParams 应包含技术指标参数', () => {
    const savedCondition = {
      filterGroup: {
        conditions: [
          {
            id: 'c1',
            op: 'AND' as const,
            fieldKey: 'pattern_morning_star',
            label: '早晨之星',
            lookbackDays: 5,
          },
        ],
      },
      nextOp: 'AND' as const,
    };

    const savedStrategyState = {
      ...getInitialState(),
      condition: savedCondition,
    };
    const { panels: _panels, ...payload } = savedStrategyState;

    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload });

    // 验证条件恢复
    expect(after.condition.filterGroup?.conditions).toHaveLength(1);
    expect(after.condition.filterGroup?.conditions[0].fieldKey).toBe('pattern_morning_star');
    expect(after.condition.filterGroup?.conditions[0].lookbackDays).toBe(5);

    // 验证 buildScreeningParams 包含 K线形态参数
    const params = buildScreeningParams(toFilterPayload(after), 'change_pct', false, 20, 0);
    expect(params['cond_pattern_morning_star']).toBe('AND');
    expect(params['pattern_morning_star']).toBe(5);
  });

  it('加载含自编指标条件的策略后，buildScreeningParams 应跳过自编指标（由客户端筛选）', () => {
    const savedCondition = {
      filterGroup: {
        conditions: [
          {
            id: 'c1',
            op: 'AND' as const,
            fieldKey: 'custom_ind_123',
            label: '自定义指标',
            source: 'custom' as const,
            sourceId: 'ind_123',
          },
          {
            id: 'c2',
            op: 'AND' as const,
            fieldKey: 'rsi_oversold',
            label: 'RSI超卖',
          },
        ],
      },
      nextOp: 'AND' as const,
    };

    const savedStrategyState = {
      ...getInitialState(),
      condition: savedCondition,
    };
    const { panels: _panels, ...payload } = savedStrategyState;

    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload });

    // 验证条件恢复
    expect(after.condition.filterGroup?.conditions).toHaveLength(2);

    // 验证 buildScreeningParams 跳过自编指标，只包含系统条件
    const params = buildScreeningParams(toFilterPayload(after), 'change_pct', false, 20, 0);
    expect(params['cond_custom_ind_123']).toBeUndefined(); // 自编指标被跳过
    expect(params['cond_rsi_oversold']).toBe('AND');
  });

  it('加载含行情指标和条件构建器条件的策略后，所有参数正确传递', () => {
    // 构造一个包含行情指标+条件构建器的策略
    const savedStrategyState = {
      ...getInitialState(),
      marketIndicators: {
        selected: ['pe_ttm', 'market_cap'],
        ranges: {
          pe_ttm: { min: '0', max: '15' },
          market_cap: { min: '50', max: '' },
        },
      },
      condition: {
        filterGroup: {
          conditions: [
            {
              id: 'c1',
              op: 'AND' as const,
              fieldKey: 'rsi_oversold',
              label: 'RSI超卖',
            },
          ],
        },
        nextOp: 'AND' as const,
      },
    };
    const { panels: _panels, ...payload } = savedStrategyState;

    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload });

    // 验证 state 恢复
    expect(after.marketIndicators.selected).toEqual(['pe_ttm', 'market_cap']);
    expect(after.marketIndicators.ranges.pe_ttm).toEqual({ min: '0', max: '15' });
    expect(after.condition.filterGroup?.conditions).toHaveLength(1);

    // 验证 buildScreeningParams 包含所有参数
    const params = buildScreeningParams(toFilterPayload(after), 'change_pct', false, 20, 0);
    expect(params['pe_ttm_min']).toBe(0);
    expect(params['pe_ttm_max']).toBe(15);
    expect(params['market_cap_min']).toBe(50 * 10000); // 单位转换
    expect(params['market_cap_max']).toBeUndefined();
    expect(params['cond_rsi_oversold']).toBe('AND');
  });

  it('loadAllCandidates 调用时，stateRef 已被 useEffect 更新为最新值（模拟异步时序）', () => {
    // 此测试验证：当 fetchFirstPage 是稳定回调（useCallback 依赖不变），
    // 但 stateRef.current 已被 useEffect 更新时，buildScreeningParams 仍能读到最新条件
    const savedCondition = {
      filterGroup: {
        conditions: [
          {
            id: 'c1',
            op: 'AND' as const,
            fieldKey: 'low_valuation',
            label: '低估值',
          },
        ],
      },
      nextOp: 'AND' as const,
    };

    const savedStrategyState = {
      ...getInitialState(),
      condition: savedCondition,
    };
    const { panels: _panels, ...payload } = savedStrategyState;

    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload });

    // 模拟 stateRef.current = after（就像 useEffect 更新一样）
    const stateRef = { current: toFilterPayload(after) };

    // 模拟 fetchScreeningData/buildScreeningParams 调用
    const params = buildScreeningParams(stateRef.current, 'change_pct', false, 20, 0);
    expect(params['cond_low_valuation']).toBe('AND');
    expect(params['sort_by']).toBe('change_pct');
    expect(params['sort_asc']).toBe(false);
    expect(params['offset']).toBe(0);
    expect(params['limit']).toBe(20);
  });

  it('多个条件顺序加载后，buildScreeningParams 保持条件顺序', () => {
    // 按顺序添加 3 个条件
    const savedCondition = {
      filterGroup: {
        conditions: [
          { id: 'c1', op: 'AND' as const, fieldKey: 'rsi_oversold', label: 'RSI超卖' },
          { id: 'c2', op: 'OR' as const, fieldKey: 'volume_breakout', label: '放量突破' },
          { id: 'c3', op: 'NOT' as const, fieldKey: 'low_valuation', label: '低估值' },
        ],
      },
      nextOp: 'AND' as const,
    };

    const savedStrategyState = {
      ...getInitialState(),
      condition: savedCondition,
    };
    const { panels: _panels, ...payload } = savedStrategyState;

    const after = rootReducer(state, { type: 'LOAD_STRATEGY', payload });

    const params = buildScreeningParams(toFilterPayload(after), 'change_pct', false, 20, 0);
    expect(params['cond_rsi_oversold']).toBe('AND');
    expect(params['cond_volume_breakout']).toBe('OR');
    expect(params['cond_low_valuation']).toBe('NOT');
  });
});