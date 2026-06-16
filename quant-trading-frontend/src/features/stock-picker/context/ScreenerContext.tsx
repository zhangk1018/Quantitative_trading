import React, { createContext, useContext, useReducer, ReactNode, useEffect } from 'react';
import { MARKET_CONFIG, STOCK_RANGE_OPTIONS } from '../config/marketConfig';
import { MARKET_INDICATORS, FINANCIAL_INDICATORS, TECHNICAL_INDICATORS, FACTOR_CONFIG } from '../config/indicatorConfig';
import { FilterOp, FilterCondition, FilterTree, genConditionId } from '../types/filterTree';
import { CustomIndicator } from '../types/customIndicator';
import { listCustomIndicators as loadFromStorage } from '../utils/customIndicatorStorage';

export interface IndicatorRange {
  min: string;
  max: string;
}

/** 当前指标 Tab（PRD 3.1.1） */
export type IndicatorTab = 'system' | 'custom';

export interface ScreenerState {
  selectedMarket: string;
  selectedBoards: string[];
  stockRange: string;
  selectedMarketIndicators: string[];
  marketIndicatorRanges: Record<string, IndicatorRange>;
  selectedFinancialIndicators: string[];
  financialIndicatorRanges: Record<string, IndicatorRange>;
  /** 技术指标已选项：指标id → 选项value（如 ma → long_align） */
  selectedTechnicalIndicators: Record<string, string>;
  /** 当前打开的技术指标配置弹窗（指标id） */
  openTechnicalModal: string | null;
  factorWeights: Record<string, number>;
  /** 条件构建器：当前选股条件树（扁平无嵌套） */
  filterTree: FilterTree | null;
  /** 条件构建器：下一个待添加条件的关系（AND/OR/NOT） */
  nextConditionOp: FilterOp;
  collapsedPanels: Record<string, boolean>;
  /** 自编指标列表（V1.0 条件构建器扩展） */
  customIndicators: CustomIndicator[];
  /** 当前激活的指标 Tab（系统预设 / 我的自编） */
  activeIndicatorTab: IndicatorTab;
}

type ScreenerAction =
  | { type: 'SET_MARKET'; payload: string }
  | { type: 'SET_BOARDS'; payload: string[] }
  | { type: 'SET_STOCK_RANGE'; payload: string }
  | { type: 'TOGGLE_MARKET_INDICATOR'; payload: string }
  | { type: 'SET_MARKET_INDICATOR_RANGE'; payload: { indicatorId: string; range: IndicatorRange } }
  | { type: 'TOGGLE_FINANCIAL_INDICATOR'; payload: string }
  | { type: 'SET_FINANCIAL_INDICATOR_RANGE'; payload: { indicatorId: string; range: IndicatorRange } }
  | { type: 'OPEN_TECHNICAL_MODAL'; payload: string }
  | { type: 'CLOSE_TECHNICAL_MODAL' }
  | { type: 'SET_TECHNICAL_INDICATOR_OPTION'; payload: { indicatorId: string; option: string } }
  | { type: 'CLEAR_TECHNICAL_INDICATOR_OPTION'; payload: string }
  | { type: 'SET_FACTOR_WEIGHT'; payload: { factorId: string; weight: number } }
  | { type: 'SET_CONDITION_TREE'; payload: FilterTree | null }
  | { type: 'SET_NEXT_CONDITION_OP'; payload: FilterOp }
  | { type: 'ADD_CONDITION'; payload: { fieldKey: FilterCondition['fieldKey']; label: string } }
  | { type: 'REMOVE_CONDITION'; payload: string }
  | { type: 'UPDATE_CONDITION_OP'; payload: { id: string; op: FilterOp } }
  | { type: 'CLEAR_CONDITIONS' }
  | { type: 'APPLY_PRESET'; payload: Omit<FilterCondition, 'id'>[] }
  | { type: 'TOGGLE_PANEL'; payload: string }
  | { type: 'RESET_ALL' }
  // V1.0 自编指标相关 actions
  | { type: 'LOAD_CUSTOM_INDICATORS'; payload: CustomIndicator[] }
  | { type: 'ADD_CUSTOM_INDICATOR'; payload: CustomIndicator }
  | { type: 'UPDATE_CUSTOM_INDICATOR'; payload: CustomIndicator }
  | { type: 'REMOVE_CUSTOM_INDICATOR'; payload: string /* id */ }
  | { type: 'SET_INDICATOR_TAB'; payload: IndicatorTab }
  | { type: 'RESOLVE_MISSING_INDICATORS' }
  | { type: 'IMPORT_CUSTOM_INDICATORS'; payload: CustomIndicator[] };

const initialState: ScreenerState = {
  selectedMarket: 'cn',
  selectedBoards: ['all'],
  stockRange: STOCK_RANGE_OPTIONS[0].value,
  selectedMarketIndicators: [],
  marketIndicatorRanges: {},
  selectedFinancialIndicators: [],
  financialIndicatorRanges: {},
  selectedTechnicalIndicators: {},
  openTechnicalModal: null,
  factorWeights: FACTOR_CONFIG.reduce((acc, factor) => ({ ...acc, [factor.id]: factor.defaultWeight }), {}),
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
  customIndicators: [],
  activeIndicatorTab: 'system',
};

function screenerReducer(state: ScreenerState, action: ScreenerAction): ScreenerState {
  switch (action.type) {
    case 'SET_MARKET': {
      const marketConfig = MARKET_CONFIG[action.payload];
      return {
        ...state,
        selectedMarket: action.payload,
        selectedBoards: marketConfig?.disabled ? [] : ['all'],
        selectedMarketIndicators: [],
        marketIndicatorRanges: {},
        selectedFinancialIndicators: [],
        financialIndicatorRanges: {},
        selectedTechnicalIndicators: {},
        openTechnicalModal: null,
        filterTree: null,
        nextConditionOp: 'AND',
      };
    }
    case 'SET_BOARDS':
      return {
        ...state,
        selectedBoards: action.payload,
      };
    case 'SET_STOCK_RANGE':
      return {
        ...state,
        stockRange: action.payload,
      };
    case 'TOGGLE_MARKET_INDICATOR': {
      const { payload: indicatorId } = action;
      const isSelected = state.selectedMarketIndicators.includes(indicatorId);
      return {
        ...state,
        selectedMarketIndicators: isSelected
          ? state.selectedMarketIndicators.filter(id => id !== indicatorId)
          : [...state.selectedMarketIndicators, indicatorId],
        marketIndicatorRanges: isSelected
          ? Object.fromEntries(Object.entries(state.marketIndicatorRanges).filter(([id]) => id !== indicatorId))
          : {
              ...state.marketIndicatorRanges,
              [indicatorId]: state.marketIndicatorRanges[indicatorId] || { min: '', max: '' },
            },
      };
    }
    case 'SET_MARKET_INDICATOR_RANGE':
      return {
        ...state,
        marketIndicatorRanges: {
          ...state.marketIndicatorRanges,
          [action.payload.indicatorId]: action.payload.range,
        },
      };
    case 'TOGGLE_FINANCIAL_INDICATOR': {
      const { payload: indicatorId } = action;
      const isSelected = state.selectedFinancialIndicators.includes(indicatorId);
      return {
        ...state,
        selectedFinancialIndicators: isSelected
          ? state.selectedFinancialIndicators.filter(id => id !== indicatorId)
          : [...state.selectedFinancialIndicators, indicatorId],
        financialIndicatorRanges: isSelected
          ? Object.fromEntries(Object.entries(state.financialIndicatorRanges).filter(([id]) => id !== indicatorId))
          : {
              ...state.financialIndicatorRanges,
              [indicatorId]: state.financialIndicatorRanges[indicatorId] || { min: '', max: '' },
            },
      };
    }
    case 'SET_FINANCIAL_INDICATOR_RANGE':
      return {
        ...state,
        financialIndicatorRanges: {
          ...state.financialIndicatorRanges,
          [action.payload.indicatorId]: action.payload.range,
        },
      };
    case 'OPEN_TECHNICAL_MODAL':
      return {
        ...state,
        openTechnicalModal: action.payload,
      };
    case 'CLOSE_TECHNICAL_MODAL':
      return {
        ...state,
        openTechnicalModal: null,
      };
    case 'SET_TECHNICAL_INDICATOR_OPTION':
      return {
        ...state,
        selectedTechnicalIndicators: {
          ...state.selectedTechnicalIndicators,
          [action.payload.indicatorId]: action.payload.option,
        },
        openTechnicalModal: null,
      };
    case 'CLEAR_TECHNICAL_INDICATOR_OPTION': {
      const next = { ...state.selectedTechnicalIndicators };
      delete next[action.payload];
      return {
        ...state,
        selectedTechnicalIndicators: next,
      };
    }
    case 'SET_FACTOR_WEIGHT':
      return {
        ...state,
        factorWeights: {
          ...state.factorWeights,
          [action.payload.factorId]: action.payload.weight,
        },
      };
    case 'SET_CONDITION_TREE':
      return {
        ...state,
        filterTree: action.payload,
      };
    case 'SET_NEXT_CONDITION_OP':
      return {
        ...state,
        nextConditionOp: action.payload,
      };
    case 'ADD_CONDITION': {
      const currentConditions = state.filterTree?.conditions || [];
      // K 2026-06-16 代码审阅建议：空列表时首条件 op 强制 'AND'（无意义，但保证数据一致性）
      // 实际过滤逻辑中首条件前无连接符，其 op 应被忽略
      const op: FilterOp = currentConditions.length === 0 ? 'AND' : state.nextConditionOp;
      const newCond: FilterCondition = {
        id: genConditionId(),
        op,
        fieldKey: action.payload.fieldKey,
        label: action.payload.label,
      };
      return {
        ...state,
        filterTree: { conditions: [...currentConditions, newCond] },
      };
    }
    case 'REMOVE_CONDITION': {
      const currentConditions = state.filterTree?.conditions || [];
      const nextConditions = currentConditions.filter((c) => c.id !== action.payload);
      return {
        ...state,
        filterTree: nextConditions.length > 0 ? { conditions: nextConditions } : null,
      };
    }
    case 'UPDATE_CONDITION_OP': {
      const currentConditions = state.filterTree?.conditions || [];
      const nextConditions = currentConditions.map((c) =>
        c.id === action.payload.id ? { ...c, op: action.payload.op } : c
      );
      return {
        ...state,
        filterTree: { conditions: nextConditions },
      };
    }
    case 'CLEAR_CONDITIONS':
      return {
        ...state,
        filterTree: null,
        nextConditionOp: 'AND',
      };
    case 'APPLY_PRESET': {
      const presetConditions: FilterCondition[] = action.payload.map((c) => ({
        ...c,
        id: genConditionId(),
      }));
      return {
        ...state,
        filterTree: { conditions: presetConditions },
      };
    }
    case 'TOGGLE_PANEL':
      return {
        ...state,
        collapsedPanels: {
          ...state.collapsedPanels,
          [action.payload]: !state.collapsedPanels[action.payload],
        },
      };
    case 'RESET_ALL':
      // K 2026-06-16 决策：自编指标属于用户私有长期资产（与"选股会话态"语义隔离），
      // 重置选股配置时保留 customIndicators + activeIndicatorTab，不受 RESET_ALL 影响
      return {
        ...initialState,
        customIndicators: state.customIndicators,
        activeIndicatorTab: state.activeIndicatorTab,
      };

    // ============================================================
    // V1.0 自编指标 actions
    // ============================================================

    case 'LOAD_CUSTOM_INDICATORS':
      return {
        ...state,
        customIndicators: action.payload,
      };

    case 'ADD_CUSTOM_INDICATOR': {
      // 按 updatedAt 倒序插入
      const next = [action.payload, ...state.customIndicators];
      return {
        ...state,
        customIndicators: next,
      };
    }

    case 'UPDATE_CUSTOM_INDICATOR': {
      const next = state.customIndicators.map((i) =>
        i.id === action.payload.id ? action.payload : i
      );
      return {
        ...state,
        customIndicators: next,
      };
    }

    case 'REMOVE_CUSTOM_INDICATOR': {
      const removedId = action.payload;
      const next = state.customIndicators.filter((i) => i.id !== removedId);
      // K 2026-06-16 代码审阅建议 2a：删除自编指标时同步扫描 filterTree.conditions，
      // 将引用该指标的条件标记为 invalid（避免 UI 重新加载时失效状态丢失）
      let nextFilterTree = state.filterTree;
      if (state.filterTree) {
        const removedFieldKey = `custom_${removedId}`;
        const nextConditions = state.filterTree.conditions.map((c) =>
          c.fieldKey === removedFieldKey
            ? { ...c, invalid: true, invalidReason: '引用的自编指标已被删除' }
            : c
        );
        nextFilterTree = { conditions: nextConditions };
      }
      return {
        ...state,
        customIndicators: next,
        filterTree: nextFilterTree,
      };
    }

    case 'SET_INDICATOR_TAB':
      return {
        ...state,
        activeIndicatorTab: action.payload,
      };

    case 'RESOLVE_MISSING_INDICATORS': {
      // K 2026-06-16 代码审阅建议 2b：基于 FilterCondition.source/sourceId 字段
      // （已完成 1c 扩展），启用失效检测逻辑：
      //   ① 自编条件引用的 sourceId 不在 state.customIndicators 中 → 标记 invalid
      //   ② 当前已标记 invalid 但引用的指标已恢复 → 清空 invalid 标记
      // 调用时机：ScreenerProvider 启动时 + 每次 LOAD_CUSTOM_INDICATORS / ADD / UPDATE / REMOVE 后
      if (!state.filterTree) return state;
      const customIds = new Set(state.customIndicators.map((i) => i.id));
      const nextConditions = state.filterTree.conditions.map((c) => {
        if (c.source !== 'custom' || !c.sourceId) return c;
        if (customIds.has(c.sourceId)) {
          // 引用恢复 → 清除失效标记
          if (c.invalid) {
            const { invalid: _i, invalidReason: _r, ...rest } = c;
            return rest as FilterCondition;
          }
          return c;
        }
        // 引用丢失 → 标记失效
        if (c.invalid) return c;
        return { ...c, invalid: true, invalidReason: '引用的自编指标已被删除' };
      });
      return {
        ...state,
        filterTree: { conditions: nextConditions },
      };
    }

    case 'IMPORT_CUSTOM_INDICATORS': {
      // 导入去重：按 id 保留 — 重复 id 跳过
      const existingIds = new Set(state.customIndicators.map((i) => i.id));
      const newOnes = action.payload.filter((i) => !existingIds.has(i.id));
      // K 2026-06-16 代码审阅建议 7a：合并后按 updatedAt 倒序，与 ADD/UPDATE 行为一致
      const merged = [...newOnes, ...state.customIndicators].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      );
      return {
        ...state,
        customIndicators: merged,
      };
    }

    default:
      return state;
  }
}

// =====================================================================
// 失效检测说明
// =====================================================================
// V1.0 过渡：FilterCondition 不含 source/sourceId/invalid 字段，失效检测由
// UI 层（ConditionBuilder.tsx）通过 state.customIndicators.some() 自行判断。
// 过渡约定：自定义指标的 fieldKey 统一以 "custom_" 前缀 + 指标 ID 组成。
// RESOLVE_MISSING_INDICATORS action 保留以便未来 FilterCondition 扩展后启用。
// =====================================================================

interface ScreenerContextType {
  state: ScreenerState;
  dispatch: React.Dispatch<ScreenerAction>;
}

const ScreenerContext = createContext<ScreenerContextType | null>(null);

export function ScreenerProvider({ children, autoLoad = true }: {
  children: ReactNode;
  autoLoad?: boolean;
}) {
  const [state, dispatch] = useReducer(screenerReducer, initialState);

  // 启动时自动从 localStorage 加载自编指标 + 触发失效检测
  useEffect(() => {
    if (autoLoad && typeof window !== 'undefined') {
      try {
        const indicators = loadFromStorage();
        dispatch({ type: 'LOAD_CUSTOM_INDICATORS', payload: indicators });
        // K 2026-06-16 代码审阅建议：启动后调用 RESOLVE_MISSING_INDICATORS，
        // 确保从 localStorage 恢复的 filterTree 中失效条件被正确标记
        // （避免 UI 重新加载时失效状态丢失）
        dispatch({ type: 'RESOLVE_MISSING_INDICATORS' });
      } catch (e) {
        // K 2026-06-16 代码审阅建议 6a：loadFromStorage 失败提示
        // V1.0 简化：仅 console.error，避免引入全局 toast 依赖；
        // V2.0 计划接入全局 notification 体系
        console.error('[ScreenerProvider] 加载自编指标失败', e);
      }
    }
  }, [autoLoad]);

  return (
    <ScreenerContext.Provider value={{ state, dispatch }}>
      {children}
    </ScreenerContext.Provider>
  );
}

export function useScreener() {
  const context = useContext(ScreenerContext);
  if (!context) {
    throw new Error('useScreener must be used within a ScreenerProvider');
  }
  return context;
}

export { screenerReducer };
