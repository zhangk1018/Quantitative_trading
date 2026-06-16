import React, { createContext, useContext, useReducer, ReactNode } from 'react';
import { MARKET_CONFIG, STOCK_RANGE_OPTIONS } from '../config/marketConfig';
import { MARKET_INDICATORS, FINANCIAL_INDICATORS, TECHNICAL_INDICATORS, FACTOR_CONFIG } from '../config/indicatorConfig';
import { FilterOp, FilterCondition, FilterTree, genConditionId } from '../types/filterTree';
export interface IndicatorRange {
  min: string;
  max: string;
}
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
}
type ScreenerAction = {
  type: 'SET_MARKET';
  payload: string;
} | {
  type: 'SET_BOARDS';
  payload: string[];
} | {
  type: 'SET_STOCK_RANGE';
  payload: string;
} | {
  type: 'TOGGLE_MARKET_INDICATOR';
  payload: string;
} | {
  type: 'SET_MARKET_INDICATOR_RANGE';
  payload: {
    indicatorId: string;
    range: IndicatorRange;
  };
} | {
  type: 'TOGGLE_FINANCIAL_INDICATOR';
  payload: string;
} | {
  type: 'SET_FINANCIAL_INDICATOR_RANGE';
  payload: {
    indicatorId: string;
    range: IndicatorRange;
  };
} | {
  type: 'OPEN_TECHNICAL_MODAL';
  payload: string;
} | {
  type: 'CLOSE_TECHNICAL_MODAL';
} | {
  type: 'SET_TECHNICAL_INDICATOR_OPTION';
  payload: {
    indicatorId: string;
    option: string;
  };
} | {
  type: 'CLEAR_TECHNICAL_INDICATOR_OPTION';
  payload: string;
} | {
  type: 'SET_FACTOR_WEIGHT';
  payload: {
    factorId: string;
    weight: number;
  };
} | {
  type: 'SET_CONDITION_TREE';
  payload: unknown;
} | {
  type: 'SET_NEXT_CONDITION_OP';
  payload: FilterOp;
} | {
  type: 'ADD_CONDITION';
  payload: {
    fieldKey: FilterCondition['fieldKey'];
    label: string;
  };
} | {
  type: 'REMOVE_CONDITION';
  payload: string;
} | {
  type: 'UPDATE_CONDITION_OP';
  payload: { id: string; op: FilterOp };
} | {
  type: 'CLEAR_CONDITIONS';
} | {
  type: 'APPLY_PRESET';
  payload: Omit<FilterCondition, 'id'>[];
} | {
  type: 'TOGGLE_PANEL';
  payload: string;
} | {
  type: 'RESET_ALL';
};
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
 filterTree: action.payload as FilterTree | null,
 };
 case 'SET_NEXT_CONDITION_OP':
 return {
 ...state,
 nextConditionOp: action.payload,
 };
 case 'ADD_CONDITION': {
   const newCond: FilterCondition = {
     id: genConditionId(),
     op: state.nextConditionOp,
     fieldKey: action.payload.fieldKey,
     label: action.payload.label,
   };
   const currentConditions = state.filterTree?.conditions || [];
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
   // 应用预设：替换当前 conditions
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
 return initialState;
 default:
 return state;
 }
}
interface ScreenerContextType {
 state: ScreenerState;
 dispatch: React.Dispatch<ScreenerAction>;
}
const ScreenerContext = createContext<ScreenerContextType | null>(null);
export function ScreenerProvider({ children }: {
 children: ReactNode;
}) {
 const [state, dispatch] = useReducer(screenerReducer, initialState);
 return (<ScreenerContext.Provider value={{ state, dispatch }}>
 {children}
 </ScreenerContext.Provider>);
}
export function useScreener() {
 const context = useContext(ScreenerContext);
 if (!context) {
 throw new Error('useScreener must be used within a ScreenerProvider');
 }
 return context;
}
export { screenerReducer };
