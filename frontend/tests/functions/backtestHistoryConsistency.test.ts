// backtestHistoryConsistency.test.ts — 回测口径统一改造单测
// 覆盖：historyFieldMap（映射/单位/prevRow）、engine 按历史行判定、dataLoader parseHistoryPayload、
//       filterTreeAdapter 剥离收敛（5 字段不再剥离）。

import { describe, it, expect } from 'vitest';
import type { FilterNode, SnapshotHistoryRow } from '../../src/features/strategy-backtest/types';
import { IndicatorCache } from '../../src/features/strategy-backtest/types';
import {
  MARKET_CAP_UNIT,
  requiredHistoryFields,
  convertHistoryRow,
  rowValue,
  rowForDate,
  findPrevRow,
  RANGE_FIELD_TO_COLUMN,
} from '../../src/features/strategy-backtest/utils/historyFieldMap';
import { evaluateFilter } from '../../src/features/strategy-backtest/engine';
import { parseHistoryPayload } from '../../src/features/strategy-backtest/utils/dataLoader';
import {
  HIGH_RISK_FUNDAMENTAL_FIELDS,
  stripUnsupportedFieldsForEngine,
  detectFundamentalFields,
} from '../../src/features/strategy-backtest/utils/filterTreeAdapter';
import { buildCustomValueByDate } from '../../src/features/strategy-backtest/utils/customIndicatorRunner';

// ==================== historyFieldMap ====================

describe('historyFieldMap', () => {
  it('convertHistoryRow：market_cap 万元→亿元，且只保留请求的字段', () => {
    const raw: SnapshotHistoryRow = {
      trade_date: '2026-09-01',
      market_cap: 5_0000_0000, // 万元（=50000亿元）
      pe_ttm: 12.5,
      close: 30.2,
    };
    const out = convertHistoryRow(raw, new Set(['trade_date', 'market_cap', 'pe_ttm']));
    expect(out.trade_date).toBe('2026-09-01');
    expect(out.market_cap).toBe(raw.market_cap! / MARKET_CAP_UNIT); // 已转亿元
    expect(out.pe_ttm).toBe(12.5);
    // 未请求字段 close 被裁剪掉
    expect(out.close).toBeUndefined();
  });

  it('rowValue：null / undefined / NaN 归一为 null', () => {
    expect(rowValue({ trade_date: 'x', pe: 3 }, 'pe')).toBe(3);
    expect(rowValue(undefined, 'pe')).toBeNull();
    expect(rowValue({ trade_date: 'x', pe: null }, 'pe')).toBeNull();
    expect(rowValue({ trade_date: 'x', pe: Number.NaN }, 'pe')).toBeNull();
  });

  it('requiredHistoryFields：返回 range 列与 pattern 所需列并集（不重复）', () => {
    const tree: FilterNode = {
      type: 'and',
      children: [
        { type: 'range', field: 'market_cap', min: 100 },
        { type: 'pattern', pattern: 'macd_golden_cross' },
        { type: 'range', field: 'pe_ttm' },
      ],
    };
    const fields = requiredHistoryFields(tree);
    expect(fields).toContain('market_cap');
    expect(fields).toContain('pe_ttm');
    expect(fields).toContain('dif');
    expect(fields).toContain('dea');
    // 无重复
    expect(new Set(fields).size).toBe(fields.length);
  });

  it('rowForDate / findPrevRow：停牌日落到该股上一有行情日', () => {
    const rows: SnapshotHistoryRow[] = [
      { trade_date: '2026-09-01', close: 10 },
      { trade_date: '2026-09-02', close: 11 },
      { trade_date: '2026-09-04', close: 12 }, // 09-03 停牌缺失
    ];
    expect(rowForDate(rows, '2026-09-02')?.close).toBe(11);
    expect(rowForDate(rows, '2026-09-03')).toBeNull(); // 停牌日无行
    // 09-04 的上一行 = 09-02（跳过停牌 09-03）
    expect(findPrevRow(rows, '2026-09-04')?.trade_date).toBe('2026-09-02');
  });
});

// ==================== engine：按历史行判定 ====================

describe('engine 按历史 Row 判定（回测口径统一）', () => {
  const snapshot = undefined as never; // range/pattern 走 row 分支，snapshot 用不到
  const bars: number[][] = [];
  const cache = {} as unknown as IndicatorCache;

  it('range 用当前日 Row 取值判定（不复用最新 snapshot）', () => {
    const row: SnapshotHistoryRow = { trade_date: '2026-09-01', pe: 12 };
    const tree: FilterNode = { type: 'range', field: 'pe', min: 0, max: 15 };
    expect(evaluateFilter(tree, snapshot, bars, cache, 0, undefined, {
      useHistoryRows: true,
      historyRow: row,
    })).toBe(true);
    expect(evaluateFilter({ ...tree, max: 11 }, snapshot, bars, cache, 0, undefined, {
      useHistoryRows: true,
      historyRow: row,
    })).toBe(false);
  });

  it('macd_golden_cross 金叉用 `<`（prev.dif<prev.dea 且 cur.dif>cur.dea），与后端一致', () => {
    const tree: FilterNode = { type: 'pattern', pattern: 'macd_golden_cross' };
    // prev dif==dea（不算金叉）
    const equal = evaluateFilter(tree, snapshot, bars, cache, 0, undefined, {
      useHistoryRows: true,
      historyRow: { trade_date: 'd2', dif: 1.2, dea: 1.0 },
      prevHistoryRow: { trade_date: 'd1', dif: 0.8, dea: 0.8 },
    });
    expect(equal).toBe(false);
    // prev dif<dea 且 cur dif>dea（真金叉）
    const g = evaluateFilter(tree, snapshot, bars, cache, 0, undefined, {
      useHistoryRows: true,
      historyRow: { trade_date: 'd2', dif: 1.2, dea: 1.0 },
      prevHistoryRow: { trade_date: 'd1', dif: 0.7, dea: 0.8 },
    });
    expect(g).toBe(true);
  });

  it('字段缺失/NaN → 条件 false（row 缺失时绝不回退 snapshot）', () => {
    const tree: FilterNode = { type: 'range', field: 'pe', min: 0, max: 15 };
    expect(evaluateFilter(tree, snapshot, bars, cache, 0, undefined, {
      useHistoryRows: true,
      historyRow: { trade_date: 'd', pe: null },
    })).toBe(false);
    expect(evaluateFilter(tree, snapshot, bars, cache, 0, undefined, {
      useHistoryRows: true,
      historyRow: undefined,
    })).toBe(false);
  });
});

// ==================== dataLoader.parseHistoryPayload ====================

describe('parseHistoryPayload', () => {
  it('解析为 Map<code, Row[]>，字段裁剪 + market_cap 转亿元', () => {
    const payload = {
      data: {
        market: 'cn',
        fields: ['trade_date', 'close', 'pe_ttm', 'market_cap'],
        stocks: [
          {
            code: '600519',
            rows: [
              { trade_date: '2026-09-01', close: 1700, pe_ttm: 30, market_cap: 2_0000_0000 },
              { trade_date: '2026-09-02', close: 1710, pe_ttm: 31, market_cap: null },
            ],
          },
        ],
      },
    };
    const fields = new Set(['trade_date', 'close', 'pe_ttm', 'market_cap']);
    const m = parseHistoryPayload(payload, fields);
    const rows = m.get('600519')!;
    expect(rows).toHaveLength(2);
    expect(rows[0].close).toBe(1700);
    // 万元→亿元
    expect(rows[0].market_cap).toBe(payload.data.stocks[0].rows[0].market_cap / MARKET_CAP_UNIT);
    // null 字段不放入（market_cap 第 2 行为 null → undefined）
    expect(rows[1].market_cap).toBeUndefined();
  });
});

// ==================== filterTreeAdapter：剥离收敛 ====================

describe('filterTreeAdapter 剥离收敛', () => {
  const tree: FilterNode = {
    type: 'and',
    children: [
      { type: 'range', field: 'pe', min: 0, max: 20 },
      { type: 'range', field: 'market_cap', min: 50 },
      { type: 'range', field: 'pe_ttm' },
      { type: 'range', field: 'turnover_rate', min: 1 },
      { type: 'range', field: 'close', min: 5 },
    ],
  };

  it('5 个基本面字段不再被剥离（HIGH_RISK_FUNDAMENTAL_FIELDS 置空）', () => {
    const { tree: kept, strippedFields } = stripUnsupportedFieldsForEngine(tree);
    expect(strippedFields).toEqual([]);
    expect(kept).toEqual(tree);
    expect(detectFundamentalFields(tree)).toEqual([]);
    expect(HIGH_RISK_FUNDAMENTAL_FIELDS.size).toBe(0);
  });
});

// ==================== buildCustomValueByDate ====================

describe('buildCustomValueByDate（自编指标日期键 zip）', () => {
  it('values[j] ↔ windowDates[j] 按日期键对齐', () => {
    const windowDates = ['2026-09-01', '2026-09-02', '2026-09-03'];
    const results = new Map([[
      'scriptA',
      { id: 'scriptA', name: 'x', errors: [], values: new Map([
        ['600519', [null, 2.5, 3.1]],
        ['000001', [5, 6, 7]],
      ]) },
    ]]);
    const out = buildCustomValueByDate(results, windowDates);
    expect(out.get('scriptA')!.get('600519')!.get('2026-09-01')).toBeNull();
    expect(out.get('scriptA')!.get('600519')!.get('2026-09-02')).toBe(2.5);
    expect(out.get('scriptA')!.get('000001')!.get('2026-09-03')).toBe(7);
    // 越界安全（window 长于 values）
    expect(out.get('scriptA')!.get('600519')!.has('2026-09-05')).toBe(false);
  });
});