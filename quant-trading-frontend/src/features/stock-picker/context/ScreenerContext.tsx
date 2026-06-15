import React, { createContext, useContext, useReducer, ReactNode } from 'react';
import { MARKET_CONFIG, STOCK_RANGE_OPTIONS } from '../config/marketConfig';
import { MARKET_INDICATORS, FINANCIAL_INDICATORS, TECHNICAL_INDICATORS, FACTOR_CONFIG } from '../config/indicatorConfig';
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
 selectedTechnicalIndicators: string[];
 factorWeights: Record<string, number>;
 conditionTree: unknown;
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
 type: 'TOGGLE_TECHNICAL_INDICATOR';
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
 selectedTechnicalIndicators: [],
 factorWeights: FACTOR_CONFIG.reduce((acc, factor) => ({ ...acc, [factor.id]: factor.defaultWeight }), {}),
 conditionTree: null,
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
 case 'TOGGLE_TECHNICAL_INDICATOR': {
 const { payload: indicatorId } = action;
 const isSelected = state.selectedTechnicalIndicators.includes(indicatorId);
 return {
 ...state,
 selectedTechnicalIndicators: isSelected
 ? state.selectedTechnicalIndicators.filter(id => id !== indicatorId)
 : [...state.selectedTechnicalIndicators, indicatorId],
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
 conditionTree: action.payload,
 };
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
