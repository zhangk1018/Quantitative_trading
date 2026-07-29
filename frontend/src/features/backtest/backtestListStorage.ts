const STORAGE_KEY = 'backtest_list';

export interface BacktestStockItem {
  stock_code: string;
  stock_name: string;
}

export function getBacktestList(): BacktestStockItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    console.warn('[Backtest] 回测股票列表加载失败');
    return [];
  }
}

export function addToBacktestList(stocks: BacktestStockItem[]): number {
  const current = getBacktestList();
  const existingCodes = new Set(current.map((s) => s.stock_code));
  const newItems = stocks.filter((s) => !existingCodes.has(s.stock_code));
  if (newItems.length === 0) return 0;
  const updated = [...current, ...newItems];
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch (e) {
    console.warn('Failed to save backtest list to localStorage', e);
  }
  return newItems.length;
}

export function removeFromBacktestList(stock_code: string): void {
  const current = getBacktestList();
  const updated = current.filter((s) => s.stock_code !== stock_code);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch (e) {
    console.warn('Failed to save backtest list to localStorage', e);
  }
}

export function clearBacktestList(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function isInBacktestList(stock_code: string): boolean {
  const list = getBacktestList();
  return list.some((s) => s.stock_code === stock_code);
}