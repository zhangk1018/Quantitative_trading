// src/features/strategy-backtest/utils/screenerToFilterNode.ts
// 选股器 ScreenerState → FilterNode AST 转换器
// 将选股器侧边栏的6个面板筛选条件转换为回测引擎可识别的 FilterNode

import type { FilterNode, RangeField, TechPattern, KlinePattern } from '../types';
import type { ScreenerState } from '@/features/stock-picker/context/ScreenerContext';
import type { CustomIndicator, IndicatorOperator } from '@/features/stock-picker/types/customIndicator';
import { MARKET_INDICATORS } from '@/features/stock-picker/config/indicatorConfig';

const BOARD_NAME_TO_CODE: Record<string, string> = {
  '上海主板': 'main',
  '深圳主板': 'main',
  '创业板': 'gem',
  '科创板': 'star',
  '北交所': 'beijing',
};

const MARKET_FIELD_MAP: Record<string, RangeField> = {
  market_cap: 'market_cap',
  price: 'close',
  change_pct: 'change_pct',
  pe_static: 'pe',
  pe_ttm: 'pe_ttm',
  pb: 'pb',
  turnover: 'turnover_rate',
  volume_ratio: 'vol_ratio_5',
};

const TECH_PATTERN_MAP: Record<string, TechPattern> = {
  'ma_long_align': 'ma_bullish',
  'macd_low_golden_cross': 'macd_golden_cross',
  'rsi_low_golden_cross': 'rsi_golden_cross',
  'boll_break_upper': 'boll_break_upper',
};

const KLINE_PATTERN_MAP: Record<string, KlinePattern> = {
  pattern_morning_star: 'morning_star',
  pattern_hammer: 'hammer',
  pattern_bullish_engulfing: 'bullish_engulfing',
};

/** 将条件运算符 + 阈值转换为 { min, max } */
function thresholdToMinMax(
  operator: IndicatorOperator,
  threshold: number | [number, number],
): { min?: number; max?: number } | { unsupported: true; reason: string } {
  switch (operator) {
    case '>':
    case '>=':
      return { min: Array.isArray(threshold) ? threshold[0] : threshold };
    case '<':
    case '<=':
      return { max: Array.isArray(threshold) ? threshold[0] : threshold };
    case '==': {
      const v = Array.isArray(threshold) ? threshold[0] : threshold;
      return { min: v, max: v };
    }
    case 'range':
      if (Array.isArray(threshold) && threshold.length >= 2) {
        return { min: threshold[0], max: threshold[1] };
      }
      return {};
    case 'cross_up':
      return { unsupported: true, reason: '上穿（cross_up）运算符回测引擎暂不支持，已忽略' };
    case 'cross_down':
      return { unsupported: true, reason: '下穿（cross_down）运算符回测引擎暂不支持，已忽略' };
    default:
      return { unsupported: true, reason: '不支持的运算符，请联系管理员' };
  }
}

export interface ConversionResult {
  tree: FilterNode | null;
  /** 硬错误：存在即阻断回测，用户必须修正后重试 */
  hardErrors: string[];
  warnings: string[];
}

export function screenerStateToFilterNode(state: ScreenerState): ConversionResult {
  const children: FilterNode[] = [];
  const warnings: string[] = [];
  const hardErrors: string[] = [];

  const marketChildren: FilterNode[] = [];
  const boards: string[] = [];
  let watchlistOnly = false;

  if (state.market.selectedBoards.length > 0 && !state.market.selectedBoards.includes('all')) {
    for (const boardName of state.market.selectedBoards) {
      const code = BOARD_NAME_TO_CODE[boardName];
      if (code && !boards.includes(code)) {
        boards.push(code);
      }
    }
  }

  if (state.market.stockRange === 'watchlist') {
    watchlistOnly = true;
  }

  if (boards.length > 0 || watchlistOnly) {
    const marketNode: FilterNode = { type: 'market' };
    if (boards.length > 0) marketNode.boards = boards;
    if (watchlistOnly) marketNode.watchlistOnly = true;
    marketChildren.push(marketNode);
  }

  children.push(...marketChildren);

  for (const indicator of MARKET_INDICATORS) {
    const range = state.marketIndicators.ranges[indicator.id];
    if (!range) continue;

    const field = MARKET_FIELD_MAP[indicator.id];
    if (!field) {
      if ((range.min !== undefined && range.min.trim() !== '') || (range.max !== undefined && range.max.trim() !== '')) {
        warnings.push(`行情指标「${indicator.label}」不支持回测引擎过滤，已忽略`);
      }
      continue;
    }

    const min = range.min !== undefined && range.min.trim() !== '' && isFinite(Number(range.min))
      ? Number(range.min)
      : undefined;
    const max = range.max !== undefined && range.max.trim() !== '' && isFinite(Number(range.max))
      ? Number(range.max)
      : undefined;

    if (min === undefined && max === undefined) continue;

    const multiplier = indicator.id === 'market_cap' ? 1 : 1;
    const rangeNode: FilterNode = { type: 'range', field };
    if (min !== undefined) rangeNode.min = min * multiplier;
    if (max !== undefined) rangeNode.max = max * multiplier;
    children.push(rangeNode);
  }

  const finRanges = state.financialIndicators.ranges;
  for (const [key, range] of Object.entries(finRanges)) {
    if ((range.min !== undefined && range.min.trim() !== '') || (range.max !== undefined && range.max.trim() !== '')) {
      hardErrors.push(`财务指标「${key}」依赖最新财报数据，回测引擎无法获取历史时点值，已阻止回测。请移除财务指标条件后重试。`);
    }
  }

  for (const [indId, option] of Object.entries(state.technical.selected)) {
    const mappingKey = `${indId}_${option}`;
    const pattern = TECH_PATTERN_MAP[mappingKey];
    if (pattern) {
      children.push({ type: 'pattern', pattern });
    } else {
      warnings.push(`技术形态「${indId}/${option}」回测引擎暂不支持，已忽略`);
    }
  }

  const conditions = state.condition.filterGroup?.conditions || [];
  for (const cond of conditions) {
    if (cond.fieldKey.startsWith('pattern_')) {
      const klinePattern = KLINE_PATTERN_MAP[cond.fieldKey];
      if (klinePattern) {
        children.push({
          type: 'kline',
          pattern: klinePattern,
          lookbackDays: cond.lookbackDays ?? 3,
        });
      } else if (cond.fieldKey === 'pattern_evening_star' || cond.fieldKey === 'pattern_bearish_engulfing') {
        warnings.push(`看跌K线形态「${cond.fieldKey}」为卖出信号，选股回测仅支持买入信号形态，已忽略`);
      } else {
        warnings.push(`K线形态「${cond.fieldKey}」回测引擎暂不支持，已忽略`);
      }
    } else if (cond.fieldKey === 'rsi_oversold') {
      children.push({ type: 'pattern', pattern: 'rsi_golden_cross' });
    } else if (cond.fieldKey === 'volume_breakout') {
      warnings.push('条件「放量突破」为复合条件，回测引擎需单独配置量价关系，已忽略');
    } else if (cond.fieldKey === 'consecutive_up') {
      warnings.push('条件「连续上涨」为复合条件，回测引擎暂不支持，已忽略');
    } else if (cond.fieldKey === 'low_valuation') {
      children.push({ type: 'range', field: 'pe', max: 30 });
      children.push({ type: 'range', field: 'pb', max: 3 });
    } else if (cond.fieldKey.startsWith('custom_')) {
      // 自编指标回测引擎支持
      if (cond.source === 'custom' && cond.sourceId) {
        // 查找该自编指标定义
        const indicator = state.custom.indicators.find((i: CustomIndicator) => i.id === cond.sourceId);
        if (indicator) {
          const converted = thresholdToMinMax(
            indicator.operator,
            indicator.defaultThreshold,
          );
          if ('unsupported' in converted) {
            warnings.push(`自编指标「${cond.label || cond.fieldKey}」${converted.reason}`);
            continue;
          }
          const { min, max } = converted;
          // 用 updatedAt 时间戳作为版本号（用于缓存失效）
          const version = new Date(indicator.updatedAt).getTime();
          children.push({
            type: 'custom_indicator',
            scriptId: cond.sourceId,
            version,
            ...(min !== undefined ? { min } : {}),
            ...(max !== undefined ? { max } : {}),
          });
        } else {
          warnings.push(`自编指标「${cond.label || cond.fieldKey}」已删除或不存在，已忽略`);
        }
      } else {
        warnings.push(`自编指标条件「${cond.label || cond.fieldKey}」回测引擎暂不支持，已忽略`);
      }
    }
  }

  if (children.length === 0) {
    return { tree: null, warnings, hardErrors };
  }

  if (children.length === 1) {
    return { tree: children[0], warnings, hardErrors };
  }

  return { tree: { type: 'and', children }, warnings, hardErrors };
}
