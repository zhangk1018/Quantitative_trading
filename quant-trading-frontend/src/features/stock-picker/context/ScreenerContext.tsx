import React, {
  createContext,
  useContext,
  useReducer,
  ReactNode,
  useCallback,
  useSyncExternalStore,
  useRef,
  useEffect,
  useMemo,
} from 'react';
import { MARKET_CONFIG, STOCK_RANGE_OPTIONS } from '../config/marketConfig';
import {
  MARKET_INDICATORS,
  FINANCIAL_INDICATORS,
  TECHNICAL_INDICATORS,
  PATTERN_INDICATORS,
  FACTOR_CONFIG,
  PANEL_KEYS,
  DEFAULT_LOOKBACK_DAYS,
  type PanelKey,
  type TechnicalOptionValue,
} from '../config/indicatorConfig';
import { FilterOp, FilterCondition, FilterGroup, genConditionId } from '../types/filterTree';
import { CustomIndicator } from '../types/customIndicator';
import { listCustomIndicators as loadFromStorage } from '../utils/customIndicatorStorage';

// ==================== 子状态类型 ====================
export interface IndicatorRange {
  min: string;
  max: string;
}

interface MarketState {
  selectedMarket: string;
  selectedBoards: string[];
  stockRange: string;
}

interface MarketIndicatorState {
  selected: string[];
  ranges: Record<string, IndicatorRange>;
}

interface FinancialIndicatorState {
  selected: string[];
  ranges: Record<string, IndicatorRange>;
}

interface TechnicalState {
  selected: Record<string, TechnicalOptionValue>;
  openModalId: string | null;
}

interface PatternState {
  selected: Record<string, number>; // 保持 number，与 LOOKBACK_OPTIONS 的 string 值转换
  panelCollapsed: boolean;
}

interface ConditionState {
  filterGroup: FilterGroup | null;
  nextOp: FilterOp;
}

interface CustomState {
  indicators: CustomIndicator[];
  activeTab: 'system' | 'custom';
}

interface FactorState {
  weights: Record<string, number>;
}

interface PanelState {
  collapsed: Record<PanelKey, boolean>;
}

export interface ScreenerState {
  market: MarketState;
  marketIndicators: MarketIndicatorState;
  financialIndicators: FinancialIndicatorState;
  technical: TechnicalState;
  patterns: PatternState;
  condition: ConditionState;
  custom: CustomState;
  factor: FactorState;
  panels: PanelState;
}

// ==================== Action 定义 ====================
type MarketAction =
  | { type: 'SET_MARKET'; payload: string }
  | { type: 'SET_BOARDS'; payload: string[] }
  | { type: 'SET_STOCK_RANGE'; payload: string };

type MarketIndicatorAction =
  | { type: 'TOGGLE_MARKET_INDICATOR'; payload: string }
  | { type: 'SET_MARKET_INDICATOR_RANGE'; payload: { indicatorId: string; range: IndicatorRange } };

type FinancialIndicatorAction =
  | { type: 'TOGGLE_FINANCIAL_INDICATOR'; payload: string }
  | { type: 'SET_FINANCIAL_INDICATOR_RANGE'; payload: { indicatorId: string; range: IndicatorRange } };

type TechnicalAction =
  | { type: 'OPEN_TECHNICAL_MODAL'; payload: string }
  | { type: 'CLOSE_TECHNICAL_MODAL' }
  | { type: 'SET_TECHNICAL_INDICATOR_OPTION'; payload: { indicatorId: string; option: TechnicalOptionValue } }
  | { type: 'CLEAR_TECHNICAL_INDICATOR_OPTION'; payload: string };

type PatternAction =
  | { type: 'TOGGLE_PATTERN'; payload: string }
  | { type: 'SET_PATTERN_LOOKBACK'; payload: { patternId: string; lookbackDays: number } }
  | { type: 'TOGGLE_PATTERN_PANEL' };

type ConditionAction =
  | { type: 'SET_CONDITION_GROUP'; payload: FilterGroup | null }
  | { type: 'SET_NEXT_CONDITION_OP'; payload: FilterOp }
  | { type: 'ADD_CONDITION'; payload: {
      fieldKey: FilterCondition['fieldKey'];
      label: string;
      source?: FilterCondition['source'];
      sourceId?: FilterCondition['sourceId'];
      op?: FilterOp;
      lookbackDays?: number;
    } }
  | { type: 'REMOVE_CONDITION'; payload: string }
  | { type: 'UPDATE_CONDITION_OP'; payload: { id: string; op: FilterOp } }
  | { type: 'CLEAR_CONDITIONS' }
  | { type: 'APPLY_PRESET'; payload: Omit<FilterCondition, 'id'>[] };

type CustomAction =
  | { type: 'LOAD_CUSTOM_INDICATORS'; payload: CustomIndicator[] }
  | { type: 'ADD_CUSTOM_INDICATOR'; payload: CustomIndicator }
  | { type: 'UPDATE_CUSTOM_INDICATOR'; payload: CustomIndicator }
  | { type: 'REMOVE_CUSTOM_INDICATOR'; payload: string }
  | { type: 'SET_INDICATOR_TAB'; payload: 'system' | 'custom' }
  | { type: 'IMPORT_CUSTOM_INDICATORS'; payload: CustomIndicator[] };

type FactorAction = { type: 'SET_FACTOR_WEIGHT'; payload: { factorId: string; weight: number } };

type PanelAction = { type: 'TOGGLE_PANEL'; payload: PanelKey };

type ResetAction = { type: 'RESET_ALL' };

export type ScreenerAction =
  | MarketAction
  | MarketIndicatorAction
  | FinancialIndicatorAction
  | TechnicalAction
  | PatternAction
  | ConditionAction
  | CustomAction
  | FactorAction
  | PanelAction
  | ResetAction;

// ==================== 子 Reducer 实现（带变化检测优化） ====================
function marketReducer(state: MarketState, action: MarketAction): MarketState {
  switch (action.type) {
    case 'SET_MARKET': {
      const config = MARKET_CONFIG[action.payload];
      const newState = {
        selectedMarket: action.payload,
        selectedBoards: config?.disabled ? [] : ['all'],
        stockRange: STOCK_RANGE_OPTIONS[0].value,
      };
      // 浅比较，若相同则返回原引用
      return (newState.selectedMarket === state.selectedMarket &&
              newState.selectedBoards === state.selectedBoards &&
              newState.stockRange === state.stockRange) ? state : newState;
    }
    case 'SET_BOARDS': {
      if (action.payload === state.selectedBoards) return state;
      return { ...state, selectedBoards: action.payload };
    }
    case 'SET_STOCK_RANGE': {
      if (action.payload === state.stockRange) return state;
      return { ...state, stockRange: action.payload };
    }
    default:
      return state;
  }
}

function marketIndicatorReducer(
  state: MarketIndicatorState,
  action: MarketIndicatorAction
): MarketIndicatorState {
  switch (action.type) {
    case 'TOGGLE_MARKET_INDICATOR': {
      const id = action.payload;
      const isSelected = state.selected.includes(id);
      if (!isSelected && state.selected.includes(id)) return state; // 不可能
      const newSelected = isSelected ? state.selected.filter(i => i !== id) : [...state.selected, id];
      const newRanges = isSelected
        ? Object.fromEntries(Object.entries(state.ranges).filter(([k]) => k !== id))
        : { ...state.ranges, [id]: state.ranges[id] || { min: '', max: '' } };
      if (newSelected === state.selected && newRanges === state.ranges) return state;
      return { selected: newSelected, ranges: newRanges };
    }
    case 'SET_MARKET_INDICATOR_RANGE': {
      const { indicatorId, range } = action.payload;
      if (state.ranges[indicatorId] === range) return state;
      return {
        ...state,
        ranges: { ...state.ranges, [indicatorId]: range },
      };
    }
    default:
      return state;
  }
}

function financialIndicatorReducer(
  state: FinancialIndicatorState,
  action: FinancialIndicatorAction
): FinancialIndicatorState {
  switch (action.type) {
    case 'TOGGLE_FINANCIAL_INDICATOR': {
      const id = action.payload;
      const isSelected = state.selected.includes(id);
      const newSelected = isSelected ? state.selected.filter(i => i !== id) : [...state.selected, id];
      const newRanges = isSelected
        ? Object.fromEntries(Object.entries(state.ranges).filter(([k]) => k !== id))
        : { ...state.ranges, [id]: state.ranges[id] || { min: '', max: '' } };
      if (newSelected === state.selected && newRanges === state.ranges) return state;
      return { selected: newSelected, ranges: newRanges };
    }
    case 'SET_FINANCIAL_INDICATOR_RANGE': {
      const { indicatorId, range } = action.payload;
      if (state.ranges[indicatorId] === range) return state;
      return {
        ...state,
        ranges: { ...state.ranges, [indicatorId]: range },
      };
    }
    default:
      return state;
  }
}

function technicalReducer(state: TechnicalState, action: TechnicalAction): TechnicalState {
  switch (action.type) {
    case 'OPEN_TECHNICAL_MODAL': {
      if (state.openModalId === action.payload) return state;
      return { ...state, openModalId: action.payload };
    }
    case 'CLOSE_TECHNICAL_MODAL': {
      if (state.openModalId === null) return state;
      return { ...state, openModalId: null };
    }
    case 'SET_TECHNICAL_INDICATOR_OPTION': {
      const { indicatorId, option } = action.payload;
      if (!indicatorId || !option) {
        console.warn('[Screener] SET_TECHNICAL_INDICATOR_OPTION 缺少必要参数');
        return state;
      }
      const newSelected = { ...state.selected, [indicatorId]: option };
      if (newSelected === state.selected && state.openModalId === null) return state;
      return { selected: newSelected, openModalId: null };
    }
    case 'CLEAR_TECHNICAL_INDICATOR_OPTION': {
      const { [action.payload]: _, ...rest } = state.selected;
      if (Object.keys(rest).length === Object.keys(state.selected).length) return state;
      return { ...state, selected: rest };
    }
    default:
      return state;
  }
}

function patternReducer(state: PatternState, action: PatternAction): PatternState {
  switch (action.type) {
    case 'TOGGLE_PATTERN': {
      const id = action.payload;
      const isSelected = id in state.selected;
      const config = PATTERN_INDICATORS.find(p => p.id === id);
      const next = { ...state.selected };
      if (isSelected) {
        delete next[id];
      } else {
        next[id] = config?.defaultLookbackDays ?? DEFAULT_LOOKBACK_DAYS;
      }
      if (next === state.selected) return state;
      return { ...state, selected: next };
    }
    case 'SET_PATTERN_LOOKBACK': {
      const { patternId, lookbackDays } = action.payload;
      if (lookbackDays <= 0) {
        console.warn('[Screener] 回溯天数必须大于0');
        return state;
      }
      if (state.selected[patternId] === lookbackDays) return state;
      return {
        ...state,
        selected: { ...state.selected, [patternId]: lookbackDays },
      };
    }
    case 'TOGGLE_PATTERN_PANEL': {
      return { ...state, panelCollapsed: !state.panelCollapsed };
    }
    default:
      return state;
  }
}

function conditionReducer(state: ConditionState, action: ConditionAction): ConditionState {
  switch (action.type) {
    case 'SET_CONDITION_GROUP': {
      if (state.filterGroup === action.payload) return state;
      return { ...state, filterGroup: action.payload };
    }
    case 'SET_NEXT_CONDITION_OP': {
      if (state.nextOp === action.payload) return state;
      return { ...state, nextOp: action.payload };
    }
    case 'ADD_CONDITION': {
      const { fieldKey, label, source, sourceId, op, lookbackDays } = action.payload;
      if (!fieldKey || !label) {
        console.warn('[Screener] ADD_CONDITION 缺少必要字段');
        return state;
      }
      const current = state.filterGroup?.conditions || [];
      const finalOp = op ?? (current.length === 0 ? 'AND' : state.nextOp);
      const newCond: FilterCondition = {
        id: genConditionId(),
        op: finalOp,
        fieldKey,
        label,
        source,
        sourceId,
        lookbackDays,
      };
      const newGroup = { conditions: [...current, newCond] };
      if (newGroup === state.filterGroup) return state;
      return { ...state, filterGroup: newGroup };
    }
    case 'REMOVE_CONDITION': {
      const current = state.filterGroup?.conditions || [];
      const filtered = current.filter(c => c.id !== action.payload);
      if (filtered.length === current.length) return state;
      const newGroup = filtered.length ? { conditions: filtered } : null;
      if (newGroup === state.filterGroup) return state;
      return { ...state, filterGroup: newGroup };
    }
    case 'UPDATE_CONDITION_OP': {
      const current = state.filterGroup?.conditions || [];
      const updated = current.map(c =>
        c.id === action.payload.id ? { ...c, op: action.payload.op } : c
      );
      if (updated === current) return state;
      return { ...state, filterGroup: { conditions: updated } };
    }
    case 'CLEAR_CONDITIONS': {
      if (state.filterGroup === null) return state;
      return { filterGroup: null, nextOp: 'AND' };
    }
    case 'APPLY_PRESET': {
      const preset = action.payload.map(c => ({ ...c, id: genConditionId() }));
      const newGroup = { conditions: preset };
      if (newGroup === state.filterGroup) return state;
      return { ...state, filterGroup: newGroup };
    }
    default:
      return state;
  }
}

function customReducer(state: CustomState, action: CustomAction): CustomState {
  switch (action.type) {
    case 'LOAD_CUSTOM_INDICATORS': {
      if (action.payload === state.indicators) return state;
      return { ...state, indicators: action.payload };
    }
    case 'ADD_CUSTOM_INDICATOR': {
      const newList = [action.payload, ...state.indicators];
      if (newList === state.indicators) return state;
      return { ...state, indicators: newList };
    }
    case 'UPDATE_CUSTOM_INDICATOR': {
      const newList = state.indicators.map(i =>
        i.id === action.payload.id ? action.payload : i
      );
      if (newList === state.indicators) return state;
      return { ...state, indicators: newList };
    }
    case 'REMOVE_CUSTOM_INDICATOR': {
      const newList = state.indicators.filter(i => i.id !== action.payload);
      if (newList.length === state.indicators.length) return state;
      return { ...state, indicators: newList };
    }
    case 'SET_INDICATOR_TAB': {
      if (state.activeTab === action.payload) return state;
      return { ...state, activeTab: action.payload };
    }
    case 'IMPORT_CUSTOM_INDICATORS': {
      const existing = new Set(state.indicators.map(i => i.id));
      const newOnes = action.payload.filter(i => !existing.has(i.id));
      if (newOnes.length === 0) return state;
      const merged = [...newOnes, ...state.indicators].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      );
      if (merged === state.indicators) return state;
      return { ...state, indicators: merged };
    }
    default:
      return state;
  }
}

function factorReducer(state: FactorState, action: FactorAction): FactorState {
  switch (action.type) {
    case 'SET_FACTOR_WEIGHT': {
      const { factorId, weight } = action.payload;
      if (weight < 0 || weight > 100) {
        console.warn('[Screener] 权重超出范围 0-100');
        return state;
      }
      if (state.weights[factorId] === weight) return state;
      return { weights: { ...state.weights, [factorId]: weight } };
    }
    default:
      return state;
  }
}

function panelReducer(state: PanelState, action: PanelAction): PanelState {
  switch (action.type) {
    case 'TOGGLE_PANEL': {
      const newCollapsed = {
        ...state.collapsed,
        [action.payload]: !state.collapsed[action.payload],
      };
      if (newCollapsed === state.collapsed) return state;
      return { collapsed: newCollapsed };
    }
    default:
      return state;
  }
}

// ==================== 声明式路由映射（增强类型安全） ====================
type SubReducerMap = {
  [K in keyof ScreenerState]: (state: ScreenerState[K], action: any) => ScreenerState[K];
};

const subReducerMap: SubReducerMap = {
  market: marketReducer,
  marketIndicators: marketIndicatorReducer,
  financialIndicators: financialIndicatorReducer,
  technical: technicalReducer,
  patterns: patternReducer,
  condition: conditionReducer,
  custom: customReducer,
  factor: factorReducer,
  panels: panelReducer,
};

// Action 到子 Reducer 的映射（使用类型断言确保完整性）
const actionToSubReducer: Record<ScreenerAction['type'], keyof ScreenerState> = {
  SET_MARKET: 'market',
  SET_BOARDS: 'market',
  SET_STOCK_RANGE: 'market',
  TOGGLE_MARKET_INDICATOR: 'marketIndicators',
  SET_MARKET_INDICATOR_RANGE: 'marketIndicators',
  TOGGLE_FINANCIAL_INDICATOR: 'financialIndicators',
  SET_FINANCIAL_INDICATOR_RANGE: 'financialIndicators',
  OPEN_TECHNICAL_MODAL: 'technical',
  CLOSE_TECHNICAL_MODAL: 'technical',
  SET_TECHNICAL_INDICATOR_OPTION: 'technical',
  CLEAR_TECHNICAL_INDICATOR_OPTION: 'technical',
  TOGGLE_PATTERN: 'patterns',
  SET_PATTERN_LOOKBACK: 'patterns',
  TOGGLE_PATTERN_PANEL: 'patterns',
  SET_CONDITION_GROUP: 'condition',
  SET_NEXT_CONDITION_OP: 'condition',
  ADD_CONDITION: 'condition',
  REMOVE_CONDITION: 'condition',
  UPDATE_CONDITION_OP: 'condition',
  CLEAR_CONDITIONS: 'condition',
  APPLY_PRESET: 'condition',
  LOAD_CUSTOM_INDICATORS: 'custom',
  ADD_CUSTOM_INDICATOR: 'custom',
  UPDATE_CUSTOM_INDICATOR: 'custom',
  REMOVE_CUSTOM_INDICATOR: 'custom',
  SET_INDICATOR_TAB: 'custom',
  IMPORT_CUSTOM_INDICATORS: 'custom',
  SET_FACTOR_WEIGHT: 'factor',
  TOGGLE_PANEL: 'panels',
};

// ==================== 根 Reducer（含后置钩子） ====================
function rootReducer(state: ScreenerState, action: ScreenerAction): ScreenerState {
  // 先处理 RESET_ALL
  if (action.type === 'RESET_ALL') {
    const newState = createInitialState(true);
    return { ...newState, custom: state.custom };
  }

  // 路由到子 Reducer
  const subKey = actionToSubReducer[action.type];
  if (!subKey) {
    console.warn(`[Screener] Unknown action type: ${(action as any).type}`);
    return state;
  }

  const subReducer = subReducerMap[subKey];
  const newSubState = subReducer(state[subKey], action);
  if (newSubState === state[subKey]) {
    return state;
  }

  // 构建新状态
  let newState = { ...state, [subKey]: newSubState };

  // 后置钩子：处理跨领域联动
  newState = afterDispatch(newState, action);

  return newState;
}

/**
 * 后置钩子：根据 Action 触发额外的状态更新
 * 当前处理：
 * - IMPORT_CUSTOM_INDICATORS / REMOVE_CUSTOM_INDICATOR：刷新条件组失效状态
 */
function afterDispatch(state: ScreenerState, action: ScreenerAction): ScreenerState {
  // 当自定义指标列表变化时，重新验证条件组
  if (action.type === 'IMPORT_CUSTOM_INDICATORS' || action.type === 'REMOVE_CUSTOM_INDICATOR') {
    const validatedGroup = resolveMissingIndicators(state.condition.filterGroup, state.custom.indicators);
    if (validatedGroup !== state.condition.filterGroup) {
      return {
        ...state,
        condition: { ...state.condition, filterGroup: validatedGroup },
      };
    }
  }
  // 也可处理 ADD_CUSTOM_INDICATOR? 但新增指标不会使现有条件失效，可忽略
  return state;
}

// ==================== 初始状态（含 Schema 校验） ====================
function isValidCustomIndicator(data: unknown): data is CustomIndicator {
  if (typeof data !== 'object' || data === null) return false;
  const obj = data as Record<string, unknown>;
  return (
    typeof obj.id === 'string' &&
    typeof obj.name === 'string' &&
    typeof obj.expr === 'string' &&
    typeof obj.updatedAt === 'string'
  );
}

function loadCustomIndicatorsSafe(): CustomIndicator[] {
  try {
    const raw = loadFromStorage();
    if (Array.isArray(raw) && raw.every(isValidCustomIndicator)) {
      return raw;
    }
    console.warn('[Screener] LocalStorage 数据格式损坏，使用默认空列表');
    return [];
  } catch (e) {
    console.error('[Screener] 加载自编指标失败', e);
    return [];
  }
}

// 同步创建初始状态（无自定义指标，异步加载）
function createInitialState(preserveCustom = false): ScreenerState {
  return {
    market: {
      selectedMarket: 'cn',
      selectedBoards: ['all'],
      stockRange: STOCK_RANGE_OPTIONS[0].value,
    },
    marketIndicators: { selected: [], ranges: {} },
    financialIndicators: { selected: [], ranges: {} },
    technical: { selected: {}, openModalId: null },
    patterns: { selected: {}, panelCollapsed: true },
    condition: { filterGroup: null, nextOp: 'AND' },
    custom: {
      indicators: preserveCustom ? [] : [], // 初始为空，异步加载
      activeTab: 'system',
    },
    factor: {
      weights: FACTOR_CONFIG.reduce((acc, f) => ({ ...acc, [f.id]: f.defaultWeight }), {}),
    },
    panels: {
      collapsed: {
        range: true,
        market: true,
        financial: true,
        technical: true,
        factor: true,
        condition: true,
        pattern: true,
      },
    },
  };
}

// ==================== 失效检测工具 ====================
export function resolveMissingIndicators(
  filterGroup: FilterGroup | null,
  customIndicators: CustomIndicator[]
): FilterGroup | null {
  if (!filterGroup) return null;
  const customIds = new Set(customIndicators.map(i => i.id));
  let changed = false;
  const nextConditions = filterGroup.conditions.map(c => {
    if (c.source !== 'custom' || !c.sourceId) return c;
    if (customIds.has(c.sourceId)) {
      // 引用存在，清除失效标记
      if (c.invalid) {
        changed = true;
        const { invalid, invalidReason, ...rest } = c;
        return rest as FilterCondition;
      }
      return c;
    } else {
      // 引用丢失
      if (!c.invalid) {
        changed = true;
        return { ...c, invalid: true, invalidReason: '引用的自编指标已被删除' };
      }
      return c;
    }
  });
  if (!changed) return filterGroup;
  return { conditions: nextConditions };
}

// ==================== Store 类（修复 dispatch 稳定性） ====================
type Listener = () => void;

class Store {
  private state: ScreenerState;
  private listeners: Set<Listener> = new Set();
  constructor(initialState: ScreenerState) {
    this.state = initialState;
    this.dispatch = this.dispatch.bind(this); // 永久绑定
  }

  getState() {
    return this.state;
  }

  dispatch(action: ScreenerAction) {
    const newState = rootReducer(this.state, action);
    if (newState !== this.state) {
      this.state = newState;
      this.listeners.forEach(listener => listener());
    }
  }

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

// ==================== Context & Provider（异步加载指标） ====================
const ScreenerContext = createContext<Store | null>(null);

export function ScreenerProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<Store | null>(null);
  if (!storeRef.current) {
    const initialState = createInitialState(false);
    storeRef.current = new Store(initialState);
  }
  const store = storeRef.current;

  // 异步加载自定义指标
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const indicators = loadCustomIndicatorsSafe();
        if (!cancelled) {
          store.dispatch({ type: 'LOAD_CUSTOM_INDICATORS', payload: indicators });
        }
      } catch (e) {
        console.error('[Screener] 异步加载自定义指标失败', e);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [store]);

  return (
    <ScreenerContext.Provider value={store}>
      {children}
    </ScreenerContext.Provider>
  );
}

// ==================== Hooks ====================

export function useScreenerSelector<T>(selector: (state: ScreenerState) => T): T {
  const store = useContext(ScreenerContext);
  if (!store) throw new Error('useScreenerSelector must be used within ScreenerProvider');

  const selectorRef = useRef(selector);
  selectorRef.current = selector;

  const getSnapshot = useCallback(() => selectorRef.current(store.getState()), [store]);
  const subscribe = useCallback((onStoreChange: () => void) => {
    return store.subscribe(onStoreChange);
  }, [store]);

  return useSyncExternalStore(subscribe, getSnapshot);
}

export function useScreenerDispatch() {
  const store = useContext(ScreenerContext);
  if (!store) throw new Error('useScreenerDispatch must be used within ScreenerProvider');
  return store.dispatch;
}

// 兼容旧版本 — @deprecated 请使用 useScreenerSelector + useScreenerDispatch 替代，下个迭代移除
export function useScreener() {
  const store = useContext(ScreenerContext);
  if (!store) throw new Error('useScreener must be used within ScreenerProvider');
  const state = useSyncExternalStore(
    useCallback((onChange) => store.subscribe(onChange), [store]),
    useCallback(() => store.getState(), [store])
  );
  return { state, dispatch: store.dispatch };
}

export { rootReducer };