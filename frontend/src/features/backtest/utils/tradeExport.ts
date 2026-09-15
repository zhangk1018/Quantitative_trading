// utils/tradeExport.ts — 交易明细导出（TXT/CSV）共享工具
// 单股交易明细（BacktestTradeLog）与批量回测汇总（BacktestUniverseResult）复用

import type { Trade } from '../backtestTypes';
import { fetchStocks } from '../../stock-detail/api';

/** 导出行类型 */
export interface TradeExportRow extends Record<string, string | number> {
  stockCode: string;
  stockName: string;
}

/** 导出用列定义（与表格展示口径一致） */
export const TRADE_EXPORT_FIELDS = ['stockCode', 'stockName', 'id', 'direction', 'entryTime', 'exitTime', 'entryPrice', 'exitPrice', 'shares', 'profitPct', 'holdDays', 'reason'] as const;
export const TRADE_EXPORT_HEADERS = ['股票代码', '股票名称', '#', '方向', '买入日期', '卖出日期', '买入价', '卖出价', '股数', '收益率(%)', '持仓天数', '触发原因'];

/** 交易记录 → 导出行（方向转中文、原因合并、空值占位） */
export function toTradeExportRow(
  t: Trade,
  stockCode: string,
  stockName: string,
): TradeExportRow {
  const directionLabel = t.direction === 'buy' ? '买入' : t.direction === 'close' ? '清仓' : '卖出';
  return {
    stockCode,
    stockName,
    id: t.id,
    direction: directionLabel,
    entryTime: t.entryTime,
    exitTime: t.exitTime || '-',
    entryPrice: t.entryPrice,
    exitPrice: t.exitPrice > 0 ? t.exitPrice : '-',
    shares: t.shares,
    profitPct: Number(t.profitPct.toFixed(2)),
    holdDays: t.holdDays,
    reason: t.direction === 'buy' ? t.entryReason : t.exitReason || t.entryReason,
  };
}

/** 过滤买入记录并按导出格式构建行数组 */
export function buildTradeExportRows(
  trades: Trade[],
  stockCode: string,
  stockName: string,
): TradeExportRow[] {
  return trades
    .filter((t) => t.direction !== 'buy')
    .map((t) => toTradeExportRow(t, stockCode || '未知', stockName || '未知'));
}

/** 判断导出行中的股票名称是否有效（非空、非占位符、非代码本身） */
function isNameValid(row: TradeExportRow): boolean {
  const name = String(row.stockName);
  return name !== '' && name !== '未知' && name !== String(row.stockCode);
}

/**
 * 反查股票名称：对名称无效（空/占位/被代码替代）的行，
 * 用 /api/stocks/?stock_codes=... 按代码批量反查真实名称并覆盖。
 * 网络失败/未命中时保留原值，不阻断导出。
 */
export async function resolveStockNames(rows: TradeExportRow[]): Promise<TradeExportRow[]> {
  if (rows.length === 0) return rows;
  const codesToLookup = Array.from(new Set(rows.filter((r) => !isNameValid(r)).map((r) => r.stockCode)));
  if (codesToLookup.length === 0) return rows;

  const nameByCode: Record<string, string> = {};
  try {
    const res = await fetchStocks({
      stock_codes: codesToLookup.join(','),
      limit: codesToLookup.length,
    });
    for (const item of res.items) {
      if (item.stock_code && item.stock_name) nameByCode[item.stock_code] = item.stock_name;
    }
  } catch {
    console.warn('[tradeExport] 股票名称反查失败，保持原值导出');
  }

  return rows.map((r) =>
    isNameValid(r) ? r : { ...r, stockName: nameByCode[r.stockCode] || r.stockName },
  );
}

/** 生成带时间戳的导出文件名 */
export function exportFilename(prefix: string, ext: 'csv' | 'txt'): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  return `${prefix}-${stamp}.${ext}`;
}

/** 创建 Blob 链接并触发下载 */
function downloadFile(content: string, mime: string, filename: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  try {
    document.body.appendChild(link);
    link.click();
  } finally {
    if (link.parentNode) document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}

/**
 * 导出交易行数组为 TXT/CSV。
 * - TXT：制表符分隔，方便直接粘贴到文本文件
 * - CSV：逗号分隔 + BOM，兼容 Excel 中文
 */
export function downloadTradeExport(
  rows: TradeExportRow[],
  ext: 'csv' | 'txt',
  prefix = 'backtest-trades',
): void {
  if (rows.length === 0) return;

  if (ext === 'txt') {
    const formatValue = (v: string | number) => String(v).replace(/\t/g, ' ');
    const body = rows.map((r) =>
      TRADE_EXPORT_FIELDS.map((f) => formatValue(r[f])).join('\t'),
    );
    downloadFile(
      [TRADE_EXPORT_HEADERS.join('\t'), ...body].join('\n'),
      'text/plain;charset=utf-8',
      exportFilename(prefix, 'txt'),
    );
  } else {
    const escapeCell = (v: string | number) => {
      const str = String(v);
      if (/[",\n\r]/.test(str)) {
        return `"${str.replace(/"/g, '""')}"`;
      }
      return str;
    };
    const body = rows.map((r) =>
      TRADE_EXPORT_FIELDS.map((f) => escapeCell(r[f])).join(','),
    );
    downloadFile(
      '\uFEFF' + [TRADE_EXPORT_HEADERS.join(','), ...body].join('\r\n'),
      'text/csv;charset=utf-8',
      exportFilename(prefix, 'csv'),
    );
  }
}