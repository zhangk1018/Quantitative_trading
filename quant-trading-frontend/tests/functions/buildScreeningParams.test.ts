/**
 * buildScreeningParams 纯函数测试
 *
 * 验证参数序列化逻辑：
 * - 上市地映射（all/主板/多选）
 * - 单位换算（market_cap/amount ×10000，普通指标 ×1）
 * - 技术指标序列化（tech_{id}=option）
 * - K线形态参数（pattern_{id}=lookbackDays）
 * - 条件构建器参数（cond_{fieldKey}=op）
 * - 范围逻辑校验（min > max 跳过）
 * - 排序/分页默认值
 */
import { describe, it, expect } from 'vitest';
import { buildScreeningParams } from '@/features/stock-picker/utils/screener';
import type { ScreenerFilterPayload } from '@/features/stock-picker/utils/screener';

/** 构造基础筛选参数（所有测试共享的结构） */
function basePayload(overrides: Partial<ScreenerFilterPayload> = {}): ScreenerFilterPayload {
  return {
    selectedBoards: ['all'],
    stockRange: 'all',
    marketIndicatorRanges: {},
    financialIndicatorRanges: {},
    selectedTechnicalIndicators: {},
    selectedPatterns: {},
    filterGroup: null,
    ...overrides,
  };
}

describe.skip('buildScreeningParams', () => {
  // ---------- 上市地映射 ----------
  it('selectedBoards=["all"] → 无 listed_board 参数', () => {
    const params = buildScreeningParams(basePayload(), 'change_pct', false, 20);
    expect(params.listed_board).toBeUndefined();
  });

  it('selectedBoards=[] → 无 listed_board 参数', () => {
    const params = buildScreeningParams(basePayload({ selectedBoards: [] }), 'change_pct', false, 20);
    expect(params.listed_board).toBeUndefined();
  });

  it('selectedBoards=["上海主板","深圳主板"] → listed_board="主板"', () => {
    const params = buildScreeningParams(
      basePayload({ selectedBoards: ['上海主板', '深圳主板'] }),
      'change_pct', false, 20,
    );
    expect(params.listed_board).toBe('主板');
  });

  it('selectedBoards=["创业板"] → listed_board="创业板"', () => {
    const params = buildScreeningParams(
      basePayload({ selectedBoards: ['创业板'] }),
      'change_pct', false, 20,
    );
    expect(params.listed_board).toBe('创业板');
  });

  it('selectedBoards=["上海主板","科创板"] → listed_board="上海主板,科创板"', () => {
    const params = buildScreeningParams(
      basePayload({ selectedBoards: ['上海主板', '科创板'] }),
      'change_pct', false, 20,
    );
    expect(params.listed_board).toBe('上海主板,科创板');
  });

  it('selectedBoards=["all","创业板"] 含 all → 忽略其他板，无 listed_board', () => {
    const params = buildScreeningParams(
      basePayload({ selectedBoards: ['all', '创业板'] }),
      'change_pct', false, 20,
    );
    expect(params.listed_board).toBeUndefined();
  });

  // ---------- 自选范围 ----------
  it('stockRange="watchlist" → watchlist_only=true', () => {
    const params = buildScreeningParams(
      basePayload({ stockRange: 'watchlist' }),
      'change_pct', false, 20,
    );
    expect(params.watchlist_only).toBe(true);
  });

  it('stockRange="all" → 无 watchlist_only', () => {
    const params = buildScreeningParams(
      basePayload({ stockRange: 'all' }),
      'change_pct', false, 20,
    );
    expect(params.watchlist_only).toBeUndefined();
  });

  // ---------- 单位换算 ----------
  it('market_cap 输入亿→转为万元（×10000）', () => {
    const params = buildScreeningParams(basePayload({
      marketIndicatorRanges: { market_cap: { min: 50, max: 500 } },
    }), 'change_pct', false, 20);
    expect(params.market_cap_min).toBe(500000);   // 50 × 10000
    expect(params.market_cap_max).toBe(5000000);  // 500 × 10000
  });

  it('amount 输入亿→转为万元（×10000）', () => {
    const params = buildScreeningParams(basePayload({
      marketIndicatorRanges: { amount: { min: 1 } },
    }), 'change_pct', false, 20);
    expect(params.amount_min).toBe(10000);  // 1 × 10000
    expect(params.amount_max).toBeUndefined();
  });

  it('普通指标（如 pe）无单位换算', () => {
    const params = buildScreeningParams(basePayload({
      financialIndicatorRanges: { pe: { min: 0, max: 15 } },
    }), 'change_pct', false, 20);
    expect(params.pe_min).toBe(0);
    expect(params.pe_max).toBe(15);
  });

  // ---------- 范围逻辑校验 ----------
  it('min > max 时跳过该指标', () => {
    const params = buildScreeningParams(basePayload({
      marketIndicatorRanges: { market_cap: { min: 500, max: 50 } },
    }), 'change_pct', false, 20);
    expect(params.market_cap_min).toBeUndefined();
    expect(params.market_cap_max).toBeUndefined();
  });

  it('isFinite 校验：NaN/Infinity 忽略', () => {
    const params = buildScreeningParams(basePayload({
      marketIndicatorRanges: {
        market_cap: { min: NaN, max: 100 },
        turnover_rate: { min: Infinity, max: 50 },
      },
    }), 'change_pct', false, 20);
    expect(params.market_cap_min).toBeUndefined();
    expect(params.market_cap_max).toBe(100 * 10000);
    expect(params.turnover_rate_min).toBeUndefined();
    expect(params.turnover_rate_max).toBe(50);
  });

  // ---------- 技术指标序列化 ----------
  it('selectedTechnicalIndicators → tech_{id}=option', () => {
    const params = buildScreeningParams(basePayload({
      selectedTechnicalIndicators: { ma: 'long_align', rsi: 'low_golden_cross' },
    }), 'change_pct', false, 20);
    expect(params.tech_ma).toBe('long_align');
    expect(params.tech_rsi).toBe('low_golden_cross');
  });

  it('空 selectedTechnicalIndicators → 无 tech_* 参数', () => {
    const params = buildScreeningParams(basePayload(), 'change_pct', false, 20);
    expect(Object.keys(params).filter((k) => k.startsWith('tech_'))).toHaveLength(0);
  });

  // ---------- K线形态参数 ----------
  it('selectedPatterns → pattern_{id}=lookbackDays', () => {
    const params = buildScreeningParams(basePayload({
      selectedPatterns: { hammer: 5, morning_star: 10 },
    }), 'change_pct', false, 20);
    expect(params.pattern_hammer).toBe(5);
    expect(params.pattern_morning_star).toBe(10);
  });

  it('空 selectedPatterns → 无 pattern_* 参数', () => {
    const params = buildScreeningParams(basePayload(), 'change_pct', false, 20);
    expect(Object.keys(params).filter((k) => k.startsWith('pattern_'))).toHaveLength(0);
  });

  // ---------- 条件构建器 ----------
  it('filterGroup.conditions → cond_{fieldKey}=op', () => {
    const params = buildScreeningParams(basePayload({
      filterGroup: {
        conditions: [
          { fieldKey: 'rsi_oversold', op: 'AND' },
          { fieldKey: 'volume_breakout', op: 'AND' },
        ],
      },
    }), 'change_pct', false, 20);
    expect(params.cond_rsi_oversold).toBe('AND');
    expect(params.cond_volume_breakout).toBe('AND');
  });

  it('filterGroup=null → 无 cond_* 参数', () => {
    const params = buildScreeningParams(basePayload(), 'change_pct', false, 20);
    expect(Object.keys(params).filter((k) => k.startsWith('cond_'))).toHaveLength(0);
  });

  it('filterGroup.conditions=[] → 无 cond_* 参数', () => {
    const params = buildScreeningParams(basePayload({
      filterGroup: { conditions: [] },
    }), 'change_pct', false, 20);
    expect(Object.keys(params).filter((k) => k.startsWith('cond_'))).toHaveLength(0);
  });

  // ---------- 排序 / 分页默认值 ----------
  it('排序和分页参数始终存在', () => {
    const params = buildScreeningParams(basePayload(), 'turnover_rate', true, 50);
    expect(params.sort_by).toBe('turnover_rate');
    expect(params.sort_asc).toBe(true);
    expect(params.offset).toBe(0);
    expect(params.limit).toBe(50);
  });

  it('自定义 offset 正确传递', () => {
    const params = buildScreeningParams(basePayload(), 'change_pct', false, 20, 40);
    expect(params.offset).toBe(40);
    expect(params.limit).toBe(20);
  });

  // ---------- 组合场景 ----------
  it('全选参数组合：主板+范围+指标+形态+条件', () => {
    const params = buildScreeningParams(basePayload({
      selectedBoards: ['上海主板', '深圳主板'],
      stockRange: 'watchlist',
      marketIndicatorRanges: { market_cap: { min: 10 }, volume: { max: 10000 } },
      financialIndicatorRanges: { pe: { max: 20 } },
      selectedTechnicalIndicators: { ma: 'golden_cross' },
      selectedPatterns: { hammer: 3 },
      filterGroup: {
        conditions: [{ fieldKey: 'volume_breakout', op: 'AND' }],
      },
    }), 'change_pct', false, 20);

    expect(params.listed_board).toBe('主板');
    expect(params.watchlist_only).toBe(true);
    expect(params.market_cap_min).toBe(100000);  // 10 × 10000
    expect(params.volume_max).toBe(10000);
    expect(params.pe_max).toBe(20);
    expect(params.tech_ma).toBe('golden_cross');
    expect(params.pattern_hammer).toBe(3);
    expect(params.cond_volume_breakout).toBe('AND');
    expect(params.sort_by).toBe('change_pct');
    expect(params.sort_asc).toBe(false);
    expect(params.offset).toBe(0);
    expect(params.limit).toBe(20);
  });
});