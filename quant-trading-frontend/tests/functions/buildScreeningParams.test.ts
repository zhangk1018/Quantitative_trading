/**
 * buildScreeningParams 纯函数测试
 *
 * 验证参数序列化逻辑：
 * - 上市地映射（all/主板/多选）
 * - 单位换算（market_cap/amount ×10000，普通指标 ×1）
 * - 技术指标序列化（tech_{id}=option）
 * - 条件构建器参数（cond_{fieldKey}=op）
 * - 排序/分页默认值
 */
import { describe, it, expect } from 'vitest';
import { buildScreeningParams } from '@/features/stock-picker/StockPickerView';
import type { ScreenerState } from '@/features/stock-picker/context/ScreenerContext';

/** 构造基础 ScreenerState（所有测试共享的结构） */
function baseState(overrides: Partial<ScreenerState> = {}): ScreenerState {
  return {
    selectedMarket: 'cn',
    selectedBoards: ['all'],
    stockRange: 'all',
    selectedMarketIndicators: [],
    marketIndicatorRanges: {},
    selectedFinancialIndicators: [],
    financialIndicatorRanges: {},
    selectedTechnicalIndicators: {},
    openTechnicalModal: null,
    factorWeights: {},
    filterGroup: null,
    nextConditionOp: 'AND',
    collapsedPanels: {},
    customIndicators: [],
    activeIndicatorTab: 'system',
    ...overrides,
  };
}

describe('buildScreeningParams', () => {
  // ---------- 上市地映射 ----------
  it('selectedBoards=["all"] → 无 listed_board 参数', () => {
    const params = buildScreeningParams(baseState(), 'change_pct', false, 20);
    expect(params.listed_board).toBeUndefined();
  });

  it('selectedBoards=[] → 无 listed_board 参数', () => {
    const params = buildScreeningParams(baseState({ selectedBoards: [] }), 'change_pct', false, 20);
    expect(params.listed_board).toBeUndefined();
  });

  it('selectedBoards=["上海主板","深圳主板"] → listed_board="主板"', () => {
    const params = buildScreeningParams(baseState({ selectedBoards: ['上海主板', '深圳主板'] }), 'change_pct', false, 20);
    expect(params.listed_board).toBe('主板');
  });

  it('selectedBoards=["创业板"] → listed_board="创业板"', () => {
    const params = buildScreeningParams(baseState({ selectedBoards: ['创业板'] }), 'change_pct', false, 20);
    expect(params.listed_board).toBe('创业板');
  });

  it('selectedBoards=["上海主板","科创板"] → listed_board="上海主板,科创板"', () => {
    const params = buildScreeningParams(baseState({ selectedBoards: ['上海主板', '科创板'] }), 'change_pct', false, 20);
    expect(params.listed_board).toBe('上海主板,科创板');
  });

  // ---------- 自选范围 ----------
  it('stockRange="watchlist" → watchlist_only=true', () => {
    const params = buildScreeningParams(baseState({ stockRange: 'watchlist' }), 'change_pct', false, 20);
    expect(params.watchlist_only).toBe(true);
  });

  it('stockRange="all" → 无 watchlist_only', () => {
    const params = buildScreeningParams(baseState({ stockRange: 'all' }), 'change_pct', false, 20);
    expect(params.watchlist_only).toBeUndefined();
  });

  // ---------- 单位换算 ----------
  it('market_cap 输入亿→转为万元（×10000）', () => {
    const params = buildScreeningParams(baseState({
      marketIndicatorRanges: { market_cap: { min: '50', max: '500' } },
    }), 'change_pct', false, 20);
    expect(params.market_cap_min).toBe(500000);   // 50 × 10000
    expect(params.market_cap_max).toBe(5000000);  // 500 × 10000
  });

  it('amount 输入亿→转为万元（×10000）', () => {
    const params = buildScreeningParams(baseState({
      marketIndicatorRanges: { amount: { min: '1', max: '' } },
    }), 'change_pct', false, 20);
    expect(params.amount_min).toBe(10000);  // 1 × 10000
    expect(params.amount_max).toBeUndefined();
  });

  it('普通指标（如 pe）无单位换算', () => {
    const params = buildScreeningParams(baseState({
      financialIndicatorRanges: { pe: { min: '0', max: '15' } },
    }), 'change_pct', false, 20);
    expect(params.pe_min).toBe(0);
    expect(params.pe_max).toBe(15);
  });

  // ---------- 技术指标序列化 ----------
  it('selectedTechnicalIndicators → tech_{id}=option', () => {
    const params = buildScreeningParams(baseState({
      selectedTechnicalIndicators: { ma: 'long_align', rsi: 'low_golden_cross' },
    }), 'change_pct', false, 20);
    expect(params.tech_ma).toBe('long_align');
    expect(params.tech_rsi).toBe('low_golden_cross');
  });

  it('空 selectedTechnicalIndicators → 无 tech_* 参数', () => {
    const params = buildScreeningParams(baseState(), 'change_pct', false, 20);
    expect(Object.keys(params).filter((k) => k.startsWith('tech_'))).toHaveLength(0);
  });

  // ---------- 条件构建器 ----------
  it('filterGroup.conditions → cond_{fieldKey}=op', () => {
    const params = buildScreeningParams(baseState({
      filterGroup: {
        conditions: [
          { id: 'c1', op: 'AND', fieldKey: 'rsi_oversold', label: 'RSI超卖' },
          { id: 'c2', op: 'AND', fieldKey: 'volume_breakout', label: '放量突破' },
        ],
      },
    }), 'change_pct', false, 20);
    expect(params.cond_rsi_oversold).toBe('AND');
    expect(params.cond_volume_breakout).toBe('AND');
  });

  it('filterGroup=null → 无 cond_* 参数', () => {
    const params = buildScreeningParams(baseState(), 'change_pct', false, 20);
    expect(Object.keys(params).filter((k) => k.startsWith('cond_'))).toHaveLength(0);
  });

  // ---------- 排序 / 分页默认值 ----------
  it('排序和分页参数始终存在', () => {
    const params = buildScreeningParams(baseState(), 'turnover_rate', true, 50);
    expect(params.sort_by).toBe('turnover_rate');
    expect(params.sort_asc).toBe(true);
    expect(params.offset).toBe(0);
    expect(params.limit).toBe(50);
  });

  // ---------- 组合场景 ----------
  it('全选参数组合：主板+范围+指标+条件', () => {
    const params = buildScreeningParams(baseState({
      selectedBoards: ['上海主板', '深圳主板'],
      stockRange: 'watchlist',
      marketIndicatorRanges: { market_cap: { min: '10', max: '' }, volume: { min: '', max: '10000' } },
      financialIndicatorRanges: { pe: { min: '', max: '20' } },
      selectedTechnicalIndicators: { ma: 'golden_cross' },
      filterGroup: {
        conditions: [
          { id: 'x1', op: 'AND', fieldKey: 'volume_breakout', label: '放量' },
        ],
      },
    }), 'change_pct', false, 20);

    // 上市地
    expect(params.listed_board).toBe('主板');
    // 自选范围
    expect(params.watchlist_only).toBe(true);
    // 单位换算 ×10000
    expect(params.market_cap_min).toBe(100000);  // 10 × 10000
    // volume 不换算
    expect(params.volume_max).toBe(10000);
    // 财务指标
    expect(params.pe_max).toBe(20);
    // 技术指标
    expect(params.tech_ma).toBe('golden_cross');
    // 条件构建器
    expect(params.cond_volume_breakout).toBe('AND');
    // 排序
    expect(params.sort_by).toBe('change_pct');
    expect(params.sort_asc).toBe(false);
    expect(params.offset).toBe(0);
    expect(params.limit).toBe(20);
  });
});