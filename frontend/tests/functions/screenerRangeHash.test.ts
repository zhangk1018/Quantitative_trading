/**
 * 候选集范围缓存键测试
 *
 * Bug 场景（K 2026-10-06）：选股条件不变，仅把所属市场从港股改为美股，
 * 点击「开始选股」后仍返回上次选出的港股。根因是 getRangeConditionHash
 * 未把 selectedMarket 纳入缓存键，导致切换市场时命中旧候选集缓存。
 */
import { describe, it, expect } from 'vitest';
import { getRangeConditionHash } from '@/features/stock-picker/hooks/useScreenerData';

function baseState() {
  return {
    selectedMarket: 'hk',
    selectedBoards: [],
    stockRange: 'all',
    marketIndicatorRanges: {},
    financialIndicatorRanges: {},
    selectedTechnicalIndicators: {},
    filterGroup: {
      conditions: [
        { id: 'c1', op: 'AND' as const, fieldKey: 'custom_ind_1', label: '自编指标', source: 'custom' as const, sourceId: 'ind_1' },
      ],
    },
  };
}

describe('getRangeConditionHash', () => {
  it('仅切换市场（hk → us）时缓存键必须变化', () => {
    const hk = getRangeConditionHash(baseState());
    const us = getRangeConditionHash({ ...baseState(), selectedMarket: 'us' });
    expect(us).not.toBe(hk);
  });

  it('市场与条件完全一致时缓存键保持稳定', () => {
    expect(getRangeConditionHash(baseState())).toBe(getRangeConditionHash(baseState()));
  });

  it('条件不变时，selectedMarket=cn 与 hk 的缓存键不同', () => {
    const cn = getRangeConditionHash({ ...baseState(), selectedMarket: 'cn' });
    const hk = getRangeConditionHash(baseState());
    expect(cn).not.toBe(hk);
  });
});