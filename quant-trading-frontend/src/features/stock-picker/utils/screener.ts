// utils/screener.ts

// ==================== 枚举常量 ====================
export enum RequestParamKeys {
  ListedBoard = 'listed_board',
  WatchlistOnly = 'watchlist_only',
  SortBy = 'sort_by',
  SortAsc = 'sort_asc',
  Offset = 'offset',
  Limit = 'limit',
  // 动态指标参数前缀
  TechPrefix = 'tech_',
  PatternPrefix = 'pattern_',
  CondPrefix = 'cond_',
}

export enum IndicatorType {
  Market = 'market',
  Financial = 'financial',
  Technical = 'technical',
  Pattern = 'pattern',
}

// ==================== 类型定义 ====================
export interface ScreenerFilterPayload {
  selectedBoards?: string[];
  stockRange?: string;
  marketIndicatorRanges?: Record<string, { min?: string; max?: string }>;
  financialIndicatorRanges?: Record<string, { min?: string; max?: string }>;
  selectedTechnicalIndicators?: Record<string, string>;
  /** 条件构建器中的条件列表，K线形态条件需包含 lookbackDays */
  filterGroup?: {
    conditions?: Array<{
      fieldKey: string;
      op: string;
      lookbackDays?: number;
    }>;
  } | null;
}

// ==================== 配置常量 ====================
export const CONFIG = {
  PAGE_SIZE: 20,
  UNIT_CONVERSION: { market_cap: 10000, amount: 10000 } as Record<string, number>,
  CSV_DANGEROUS_PREFIXES: ['=', '+', '-', '@', '\t', '\r', '＝', '＋', '－', '＠'] as const,
  REQUEST_TIMEOUT: 10000,
  DEBOUNCE_DELAY: 300,
  /** 字段默认排序方向：true=升序，false=降序 */
  DEFAULT_SORT_DIR: {
    change_pct: false,
    stock_code: true,
    market_cap: false,
    turnover_rate: false,
    pe: false,
    amount: false,
  } as Record<string, boolean>,
} as const;

// ==================== 核心函数 ====================
/**
 * 构建后端请求参数（纯函数）
 * 增加范围逻辑校验（min > max 跳过）
 */
export function buildScreeningParams(
  state: ScreenerFilterPayload,
  sortBy: string,
  sortAsc: boolean,
  limit: number,
  offset: number = 0,
): Record<string, unknown> {
  const {
    selectedBoards = [],
    stockRange,
    marketIndicatorRanges = {},
    financialIndicatorRanges = {},
    selectedTechnicalIndicators = {},
    filterGroup,
  } = state;

  const params: Record<string, unknown> = {};

  // 上市地
  if (selectedBoards.length > 0 && !selectedBoards.includes('all')) {
    const boards = selectedBoards.filter((b) => b !== 'all');
    if (boards.length > 0) {
      if (boards.length === 2 && boards.includes('上海主板') && boards.includes('深圳主板')) {
        params[RequestParamKeys.ListedBoard] = '主板';
      } else {
        params[RequestParamKeys.ListedBoard] = boards.join(',');
      }
    }
  }

  if (stockRange === 'watchlist') {
    params[RequestParamKeys.WatchlistOnly] = true;
  }

  // 行情指标（单位转换 + 数值校验 + 范围逻辑）
  const { UNIT_CONVERSION } = CONFIG;
  Object.entries(marketIndicatorRanges).forEach(([key, range]) => {
    // 空字符串表示用户未填写，不应该当作 0 处理
    const min =
      range.min !== undefined && range.min.trim() !== '' && isFinite(Number(range.min))
        ? Number(range.min)
        : undefined;
    const max =
      range.max !== undefined && range.max.trim() !== '' && isFinite(Number(range.max))
        ? Number(range.max)
        : undefined;
    // 校验 min > max
    if (min !== undefined && max !== undefined && min > max) {
      console.warn(`[buildScreeningParams] 指标 ${key} 最小值(${min})大于最大值(${max})，忽略该条件`);
      return;
    }
    const multiplier = UNIT_CONVERSION[key] || 1;
    if (min !== undefined) params[`${key}_min`] = min * multiplier;
    if (max !== undefined) params[`${key}_max`] = max * multiplier;
  });

  // 财务指标（无单位转换）
  Object.entries(financialIndicatorRanges).forEach(([key, range]) => {
    const min =
      range.min !== undefined && range.min.trim() !== '' && isFinite(Number(range.min))
        ? Number(range.min)
        : undefined;
    const max =
      range.max !== undefined && range.max.trim() !== '' && isFinite(Number(range.max))
        ? Number(range.max)
        : undefined;
    if (min !== undefined && max !== undefined && min > max) {
      console.warn(`[buildScreeningParams] 指标 ${key} 最小值(${min})大于最大值(${max})，忽略该条件`);
      return;
    }
    if (min !== undefined) params[`${key}_min`] = min;
    if (max !== undefined) params[`${key}_max`] = max;
  });

  // 技术指标
  Object.entries(selectedTechnicalIndicators).forEach(([id, option]) => {
    params[`${RequestParamKeys.TechPrefix}${id}`] = option;
  });
  // 条件构建器（含 K线形态 — 统一由 filterGroup.conditions 管理，不再有独立 patterns.selected）
  if (filterGroup?.conditions) {
    filterGroup.conditions.forEach((cond) => {
      params[`${RequestParamKeys.CondPrefix}${cond.fieldKey}`] = cond.op;
      // K线形态：额外发送 pattern_* 参数（PatternPrefix 已含 pattern_ 前缀）
      if (cond.fieldKey.startsWith('pattern_')) {
        const patternId = cond.fieldKey.replace('pattern_', '');
        params[`${RequestParamKeys.PatternPrefix}${patternId}`] = cond.lookbackDays ?? 3;
      }
    });
  }

  params[RequestParamKeys.SortBy] = sortBy;
  params[RequestParamKeys.SortAsc] = sortAsc;
  params[RequestParamKeys.Offset] = offset;
  params[RequestParamKeys.Limit] = limit;

  return params;
}

// ==================== 格式化工具 ====================
export function formatMarketCap(value: number | null | undefined): string {
  if (value == null || !isFinite(value)) return '-';
  return `${(value / 10000).toFixed(2)}亿`;
}

export function formatNumber(value: number | null | undefined, decimals = 2): string {
  if (value == null || !isFinite(value)) return '-';
  return Number(value).toFixed(decimals);
}

// ==================== CSV 导出（修复资源泄漏） ====================
export function exportToCsv<T extends Record<string, any>>(
  items: T[],
  options?: { headers?: string[]; fields?: string[]; filename?: string },
): void {
  if (!items.length) {
    console.warn('无数据可导出');
    return;
  }

  const { headers, fields, filename } = options || {};
  const fieldKeys = fields || Object.keys(items[0]);
  const headerRow = headers || fieldKeys;

  const escapeCell = (value: unknown): string => {
    if (value == null) return '';
    let str = String(value);
    if (str.length > 10000) str = str.slice(0, 10000) + '…';
    const dangerous = CONFIG.CSV_DANGEROUS_PREFIXES as readonly string[];
    if (dangerous.some((p) => str.startsWith(p))) {
      str = `'${str}`;
    }
    if (/[",\n\r]/.test(str)) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const rows = items.map((item) =>
    fieldKeys.map((key) => escapeCell(item[key])).join(','),
  );
  const csvContent = [headerRow.join(','), ...rows].join('\r\n');
  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = filename || `screener-result-${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.csv`;

  try {
    document.body.appendChild(link);
    link.click();
  } finally {
    // 确保无论点击是否成功都移除 link 并释放 URL
    if (link.parentNode) {
      document.body.removeChild(link);
    }
    URL.revokeObjectURL(url); // revoke 即使多次调用也无副作用
  }
}