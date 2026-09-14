/**
 * 股票名称排除工具：判断股票是否应在选股/回测中被剔除。
 *
 * 剔除范围（据诊断需求）：名称含 ST / *ST / 退（退市整理）。
 * 名称统一转大写后匹配 `ST` 或 `退`。用于选股视图候选池与回测买入候选池
 * 在「计算自编指标之前」统一剔除，因为自编指标公式层拿不到股票名（仅 OHLCV）。
 */
export function isExcludedStockName(name: string | null | undefined): boolean {
  if (!name) return false;
  const upper = name.toUpperCase();
  return upper.includes('ST') || upper.includes('退');
}