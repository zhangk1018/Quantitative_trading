/**
 * stockSearchOptions.ts — PDCA 模块股票「代码/名称」搜索选项统一构造
 *
 * 统一 A股/港股/美股三市场代码对应的 antic Select/AutoComplete 选项与名称提取，
 * 避免各表单各自解析 label 导致风格不一致（如用纯数字正则提取名称会破坏港股 `.HK`）。
 */
import type { StockSearchResult } from '../types';

export interface StockSearchOption {
  value: string;
  label: string;
  code: string;
  /** 独立的股票名称字段，避免从 label 反解析（label 为 `${code} ${name}`，港股/美股代码不是纯数字） */
  name: string;
}

/** 把后端搜索结果构造成 Select 选项（携带 name，供选中后回填标的名称） */
export function buildStockOptions(results: StockSearchResult[]): StockSearchOption[] {
  return results.map((s) => ({
    value: s.code,
    label: `${s.code} ${s.name}`,
    code: s.code,
    name: s.name,
  }));
}

/** 从选项提取标的名称（优先用 promise 好的 name，兜底从 label 切分） */
export function pickStockName(option: { name?: string; label?: string }): string {
  if (option.name) return option.name;
  const label = option.label ?? '';
  return label.split(/\s+/).slice(1).join(' ').trim() || label;
}