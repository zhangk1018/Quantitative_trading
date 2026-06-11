/**
 * strategyStorage.ts - 选股策略存储抽象层
 *
 * 提供 StrategyStorage 接口 + localStorage 实现 + 短码编解码 + 字段白名单校验。
 * Phase 1：纯前端，无后端依赖。Phase 2 可替换为 HttpStrategyStorage。
 *
 * 关联设计：docs/design/CUSTOM_INDICATOR_AND_STRATEGY_DESIGN.md
 */

import type { Strategy, ScreenerFilters } from '../types';

// ============================================
// 字段白名单（与 mocks/meta.ts 对齐）
// ============================================

/**
 * 有效的 pattern / momentum / break 字段白名单
 * ⚠️ 三处定义需保持同步：后端 meta.py / 前端 mocks/meta.ts / 本文件
 */
export const VALID_PATTERN_KEYS: ReadonlySet<string> = new Set([
  // K线形态（单K）
  'pattern_morning_star',
  'pattern_evening_star',
  'pattern_bullish_engulfing',
  'pattern_bearish_engulfing',
  'pattern_hammer',
  'pattern_hanging_man',
  'pattern_doji',
  'pattern_shooting_star',
  // 突破类
  'break_high_20',
  'break_high_60',
  'break_high_120',
  'break_high_250',
  'break_low_20',
  'break_low_60',
  // 连续性
  'consec_up_3',
  'consec_up_5',
  'consec_down_3',
  'consec_down_5',
  // 量能
  'vol_ratio_5',
  'vol_up_3',
  'vol_up_5',
  'vol_down_3',
  // 动量
  'momentum_5',
  'momentum_10',
  'momentum_20',
]);

// ============================================
// 导入结果类型
// ============================================

export interface ImportResult {
  strategy: Strategy;
  warnings: string[];
}

// ============================================
// 存储接口（便于未来替换为 HTTP 实现）
// ============================================

export interface StrategyStorage {
  list(): Strategy[];
  get(id: string): Strategy | null;
  save(strategy: Strategy): void;
  delete(id: string): void;
  /** 导出为 URL 安全 Base64 短码 */
  exportShortCode(id: string): string;
  /** 导出为格式化 JSON 字符串 */
  exportJSON(id: string): string;
  /** 从短码或 JSON 字符串导入（自动识别） */
  import(raw: string): ImportResult;
  /** 触发浏览器下载 .json 文件 */
  downloadAsFile(id: string, filename?: string): void;
  /** 复制短码到剪贴板 */
  copyShortCodeToClipboard(id: string): Promise<void>;
}

// ============================================
// 工具函数
// ============================================

const STORAGE_KEY = 'quant_trading:strategies';
const MAX_STRATEGIES = 50;

/** 生成 UUID v4 */
function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  // 兜底
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** URL 安全 Base64 编码（替换 +/=） */
function b64UrlEncode(str: string): string {
  return btoa(unescape(encodeURIComponent(str)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/** URL 安全 Base64 解码 */
function b64UrlDecode(b64: string): string {
  const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
  const standard = padded.replace(/-/g, '+').replace(/_/g, '/');
  return decodeURIComponent(escape(atob(standard)));
}

/** 检测字符串是否为 JSON */
function isJSON(s: string): boolean {
  const trimmed = s.trim();
  return trimmed.startsWith('{') || trimmed.startsWith('[');
}

/** 校验 strategy 字段，剔除失效字段并返回警告 */
function validateStrategy(s: Strategy): { validated: Strategy; warnings: string[] } {
  const warnings: string[] = [];

  const validPatterns = (s.filters?.patterns ?? []).filter((p) => {
    if (VALID_PATTERN_KEYS.has(p)) return true;
    warnings.push(`字段 ${p} 在当前版本不存在，已忽略`);
    return false;
  });

  const validated: Strategy = {
    ...s,
    id: s.id || uuid(),
    name: (s.name || '未命名策略').toString().slice(0, 100),
    filters: {
      boards: Array.isArray(s.filters?.boards) ? s.filters.boards : [],
      industries: Array.isArray(s.filters?.industries) ? s.filters.industries : [],
      patterns: validPatterns,
      sortBy: s.filters?.sortBy ?? 'score',
      sortOrder: s.filters?.sortOrder === 'asc' ? 'asc' : 'desc',
      topN: Math.max(1, Math.min(500, Number(s.filters?.topN) || 20)),
    },
    createdAt: s.createdAt || new Date().toISOString(),
    updatedAt: s.updatedAt || new Date().toISOString(),
  };

  return { validated, warnings };
}

/** 检测并解决 ID 冲突 */
function resolveIdConflict(s: Strategy, existing: Strategy[]): Strategy {
  const existingIds = new Set(existing.map((e) => e.id));
  if (!existingIds.has(s.id)) return s;
  return {
    ...s,
    id: uuid(),
    name: `${s.name} (导入)`,
    createdAt: new Date().toISOString(),
  };
}

// ============================================
// LocalStorage 实现
// ============================================

class LocalStorageStrategyStorage implements StrategyStorage {
  /** 读取所有策略（容错：解析失败返回空数组） */
  private readAll(): Strategy[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      console.error('[strategyStorage] 读取失败:', err);
      return [];
    }
  }

  /** 写入所有策略（容量保护：超过上限保留最新的） */
  private writeAll(strategies: Strategy[]): void {
    if (strategies.length > MAX_STRATEGIES) {
      console.warn(
        `[strategyStorage] 策略数量超过 ${MAX_STRATEGIES} 条上限，仅保留最新 ${MAX_STRATEGIES} 条`
      );
      strategies = strategies
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
        .slice(0, MAX_STRATEGIES);
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(strategies));
  }

  list(): Strategy[] {
    return this.readAll().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  get(id: string): Strategy | null {
    return this.readAll().find((s) => s.id === id) ?? null;
  }

  save(strategy: Strategy): void {
    const all = this.readAll();
    const idx = all.findIndex((s) => s.id === strategy.id);
    const updated: Strategy = {
      ...strategy,
      updatedAt: new Date().toISOString(),
    };
    if (idx >= 0) {
      all[idx] = updated;
    } else {
      all.push(updated);
    }
    this.writeAll(all);
  }

  delete(id: string): void {
    const all = this.readAll().filter((s) => s.id !== id);
    this.writeAll(all);
  }

  exportShortCode(id: string): string {
    const strategy = this.get(id);
    if (!strategy) throw new Error(`策略不存在: ${id}`);
    return b64UrlEncode(JSON.stringify(strategy));
  }

  exportJSON(id: string): string {
    const strategy = this.get(id);
    if (!strategy) throw new Error(`策略不存在: ${id}`);
    return JSON.stringify(strategy, null, 2);
  }

  import(raw: string): ImportResult {
    const trimmed = raw.trim();
    if (!trimmed) throw new Error('导入内容为空');

    let parsed: unknown;
    try {
      // 优先尝试 JSON 直接解析
      if (isJSON(trimmed)) {
        parsed = JSON.parse(trimmed);
      } else {
        // 兜底：尝试 Base64 解码
        parsed = JSON.parse(b64UrlDecode(trimmed));
      }
    } catch (err) {
      throw new Error('导入内容格式无效（既不是 JSON 也不是短码）');
    }

    // 兼容数组包裹
    const obj: Strategy = Array.isArray(parsed)
      ? (parsed[0] as Strategy)
      : (parsed as Strategy);

    if (!obj || typeof obj !== 'object' || !('filters' in obj)) {
      throw new Error('导入内容缺少 filters 字段，格式不合法');
    }

    // 字段校验
    const { validated, warnings } = validateStrategy(obj);

    // ID 冲突处理
    const existing = this.readAll();
    const final = resolveIdConflict(validated, existing);

    return { strategy: final, warnings };
  }

  downloadAsFile(id: string, filename?: string): void {
    const strategy = this.get(id);
    if (!strategy) throw new Error(`策略不存在: ${id}`);
    const json = JSON.stringify(strategy, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename ?? `strategy-${strategy.name}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async copyShortCodeToClipboard(id: string): Promise<void> {
    const code = this.exportShortCode(id);
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(code);
    } else {
      // 兜底：execCommand
      const ta = document.createElement('textarea');
      ta.value = code;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
  }
}

// ============================================
// 导出单例
// ============================================

export const strategyStorage: StrategyStorage = new LocalStorageStrategyStorage();

/** 工具：新建空白策略（不写入存储） */
export function createEmptyStrategy(name: string, filters: ScreenerFilters): Strategy {
  const now = new Date().toISOString();
  return {
    id: uuid(),
    name,
    filters,
    createdAt: now,
    updatedAt: now,
  };
}
