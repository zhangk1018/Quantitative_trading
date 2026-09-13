// src/features/strategy-backtest/utils/historyFieldMap.ts
// 回测逐日判定字段映射：/api/snapshot/history 宽表列 ↔ 引擎 RangeField / TechPattern
// 与选股视图 /api/stocks/（同一宽表导出）口径统一。
//
// 核心约定：
// - /history 返回 stock_daily_snapshot 的预计算字段（与 /api/stocks/ 同源）。
// - market_cap 数据端为「万元」，而 FilterNode 阈值语义为「亿元」：见 MARKET_CAP_UNIT。
// - null / undefined / 未请求字段 统一归一为 null，参与条件判定一律视为 false。

import type { FilterNode, RangeField, SnapshotHistoryRow, TechPattern } from '../types';

/** trade_date 在历史快照行中的键 */
export const TRADE_DATE_KEY = 'trade_date';

/** 单位换算：数据端 market_cap 为万元，FilterNode 阈值语义为亿元 */
export const MARKET_CAP_UNIT = 10000;

/** historyByDate 内层行（宽表单日快照，字段名与后端列一致） */
export type HistoryRow = SnapshotHistoryRow;

/** 映射 RangeField → /history 列名 */
export const RANGE_FIELD_TO_COLUMN: Record<RangeField, string> = {
  market_cap: 'market_cap',
  close: 'close',
  change_pct: 'change_pct',
  pe: 'pe',
  pe_ttm: 'pe_ttm',
  pb: 'pb',
  turnover_rate: 'turnover_rate',
  vol_ratio_5: 'vol_ratio_5',
};

/** 映射 TechPattern → 判定所需 /history 列（复刻后端 _update_tech_patterns SQL） */
export const TECH_PATTERN_REQUIRED_COLUMNS: Record<TechPattern, string[]> = {
  ma_bullish: ['ma5', 'ma10', 'ma20'],
  macd_golden_cross: ['dif', 'dea'],
  rsi_golden_cross: ['rsi_6', 'rsi_12'],
  boll_break_upper: ['close', 'boll_upper'],
};

/**
 * 计算给定 filterTree 实际需要的 /history 字段集合（用于 fields 裁剪，减少传输量）。
 * - range 用其列名；pattern 用其判定所需列集合。
 * - kline / market / custom_indicator 不走 /history 字段，不参与。
 */
export function requiredHistoryFields(tree: FilterNode): string[] {
  const set = new Set<string>();
  const visit = (n: FilterNode): void => {
    switch (n.type) {
      case 'and':
      case 'or':
        n.children.forEach(visit);
        break;
      case 'not':
        visit(n.child);
        break;
      case 'range':
        set.add(RANGE_FIELD_TO_COLUMN[n.field]);
        break;
      case 'pattern':
        TECH_PATTERN_REQUIRED_COLUMNS[n.pattern].forEach((c) => set.add(c));
        break;
      default:
        break;
    }
  };
  visit(tree);
  return Array.from(set);
}

/**
 * 将后端单日快照行转换为引擎取值行（不可变）：
 * - market_cap 从「万元」→「亿元」（与 FilterNode 阈值语义一致）
 * - 其余数值原样透传
 * - 未请求字段 / 为 null 的字段不放入（reduced 传输量 + 统一 null 语义）
 */
export function convertHistoryRow(
  row: HistoryRow,
  fields: ReadonlySet<string>,
): HistoryRow {
  const out: HistoryRow = { [TRADE_DATE_KEY]: String(row[TRADE_DATE_KEY] ?? '') };
  for (const f of fields) {
    if (f === TRADE_DATE_KEY) continue;
    const raw = row[f];
    if (raw == null) continue;
    if (f === 'market_cap' && typeof raw === 'number') {
      out[f] = raw / MARKET_CAP_UNIT;
    } else {
      out[f] = raw;
    }
  }
  return out;
}

/** 取行中字段数值，null / undefined / NaN 统一归一为 null */
export function rowValue(row: HistoryRow | undefined, column: string): number | null {
  if (!row) return null;
  const raw = row[column];
  if (raw == null) return null;
  const n = Number(raw);
  return Number.isNaN(n) ? null : n;
}

/** 行日期键 */
export function dateOfRow(row: HistoryRow): string {
  return String(row[TRADE_DATE_KEY]);
}

/**
 * 在股票升序行数组中查找 trade_date === dateKey 的行（二分）。
 * @returns 命中返回该行；无则 null
 */
export function rowForDate(
  sortedRows: HistoryRow[],
  dateKey: string,
): HistoryRow | null {
  let lo = 0;
  let hi = sortedRows.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const d = String(sortedRows[mid][TRADE_DATE_KEY]);
    if (d === dateKey) return sortedRows[mid];
    if (d < dateKey) lo = mid + 1;
    else hi = mid - 1;
  }
  return null;
}

/**
 * 在股票升序行数组中找到「严格早于 dateKey」的最近一行（即该股上一有行情日）。
 * 与后端 pattern 预计算按"每只股票自身行序（LEAD/LAG OVER PARTITION BY code）"
 * 取上一有行情日 的口径一致（停牌日该股无行，自然落到前一有行情日）。
 *
 * @param sortedRows 该股升序行数组（含 trade_date）
 * @param dateKey    目标交易日 YYYY-MM-DD
 * @returns 该股在 dateKey 之前的最近一行；无则 null
 */
export function findPrevRow(
  sortedRows: HistoryRow[],
  dateKey: string,
): HistoryRow | null {
  let lo = 0;
  let hi = sortedRows.length - 1;
  let ans: HistoryRow | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (String(sortedRows[mid][TRADE_DATE_KEY]) < dateKey) {
      ans = sortedRows[mid];
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}