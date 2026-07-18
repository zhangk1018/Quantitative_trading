// src/features/strategy-backtest/utils/filterTreeAdapter.ts
// 选股器 FilterTree → FilterNode AST 转换器
// 采用 Visitor 模式，支持插件化节点类型扩展
// 职责分层契约：tree 参数仅承载选股逻辑，不包含策略执行参数

import type { FilterNode, RangeField, TechPattern, KlinePattern } from '../types';

// ==================== 常量 ====================

/** 高风险基本面字段（硬阻断，需前端验证） */
export const HIGH_RISK_FUNDAMENTAL_FIELDS: Set<string> = new Set([
  'pe', 'pe_ttm', 'pb', 'market_cap', 'turnover_rate', 'vol_ratio_5',
]);

/** 低风险属性字段（允许通过，可用历史快照回溯） */
export const LOW_RISK_FUNDAMENTAL_FIELDS: Set<string> = new Set([
  'board', 'is_st', 'listed_board',
]);

/** 合法板块枚举 */
const VALID_BOARDS: ReadonlySet<string> = new Set(['main', 'gem', 'star', 'beijing']);

/** 合法技术形态枚举 */
const VALID_TECH_PATTERNS: ReadonlySet<string> = new Set([
  'ma_bullish', 'macd_golden_cross', 'rsi_golden_cross', 'boll_break_upper',
]);

/** 合法 K 线形态枚举 */
const VALID_KLINE_PATTERNS: ReadonlySet<string> = new Set([
  'morning_star', 'hammer', 'bullish_engulfing', 'piercing_line', 'three_white_soldiers',
]);

/** 合法 RangeField 枚举 */
const VALID_RANGE_FIELDS: ReadonlySet<string> = new Set([
  'market_cap', 'close', 'change_pct', 'pe', 'pe_ttm', 'pb', 'turnover_rate', 'vol_ratio_5',
]);

/**
 * 各字段的合理数值范围 [min, max]
 * 基于 A 股历史数据统计，超出此范围可能为异常数据，但仅发出警告而非阻断
 * 注意：范围设定相对宽松，避免因历史极端价格（如退市整理期、老八股等）误阻断
 */
const FIELD_RANGE_LIMITS: Record<string, [number, number]> = {
  market_cap: [0, 1_000_000],    // 亿元（放宽下限至0，上限至1e6覆盖极端情况）
  close:      [0, 100_000],      // 元（放宽上限至10万元/股）
  change_pct: [-100, 100],       // 百分比
  pe:         [-1_000, 10_000], // 倍（亏损企业 PE 为负值，下限 -1000 覆盖极端值）
  pe_ttm:     [0, 10_000],       // 倍
  pb:         [0, 1_000],        // 倍
  turnover_rate: [0, 100],       // 百分比
  vol_ratio_5:  [0, 200],        // 无量纲
};

// ==================== 校验器 ====================

/** 校验 FilterNode 深度和大小，以及字段值合法性 */
export function validateFilterNode(
  node: FilterNode,
  depth: number,
  maxDepth = 10,
  maxSize = 2048,
): void {
  if (depth > maxDepth) {
    throw new Error(`选股条件递归深度超过限制 (${maxDepth}层)，请简化后重试`);
  }

  const serialized = JSON.stringify(node);
  if (serialized.length > maxSize) {
    throw new Error(`选股条件序列化长度超过限制 (${maxSize}字节)，请简化后重试`);
  }

  switch (node.type) {
    case 'and':
    case 'or':
      if (!Array.isArray(node.children) || node.children.length === 0) {
        throw new Error(`${node.type} 节点缺少 children 数组`);
      }
      for (const child of node.children) {
        validateFilterNode(child, depth + 1, maxDepth, maxSize);
      }
      break;
    case 'not':
      if (!node.child) {
        throw new Error('not 节点缺少 child');
      }
      validateFilterNode(node.child, depth + 1, maxDepth, maxSize);
      break;
    case 'range':
      // 校验 field 合法性
      if (!VALID_RANGE_FIELDS.has(node.field)) {
        throw new Error(`非法 range 字段：${node.field}`);
      }
      // 校验数值范围（警告而非阻断，避免因历史极端价格误阻断）
      if (node.min !== undefined) {
        const limits = FIELD_RANGE_LIMITS[node.field];
        if (limits && (node.min < limits[0] || node.min > limits[1])) {
          console.warn(`[FilterTree] ${node.field} 最小值 ${node.min} 超出合理范围 [${limits[0]}, ${limits[1]}]，允许通过`);
        }
      }
      if (node.max !== undefined) {
        const limits = FIELD_RANGE_LIMITS[node.field];
        if (limits && (node.max < limits[0] || node.max > limits[1])) {
          console.warn(`[FilterTree] ${node.field} 最大值 ${node.max} 超出合理范围 [${limits[0]}, ${limits[1]}]，允许通过`);
        }
      }
      break;
    case 'pattern':
      if (!VALID_TECH_PATTERNS.has(node.pattern)) {
        throw new Error(`非法技术形态：${node.pattern}`);
      }
      break;
    case 'kline':
      if (!VALID_KLINE_PATTERNS.has(node.pattern)) {
        throw new Error(`非法 K 线形态：${node.pattern}`);
      }
      if (node.lookbackDays < 1 || node.lookbackDays > 120) {
        throw new Error(`K 线回溯天数 ${node.lookbackDays} 超出合理范围 [1, 120]`);
      }
      break;
    case 'market':
      if (node.boards) {
        if (!Array.isArray(node.boards)) {
          throw new Error('market 节点 boards 必须是数组');
        }
        for (const board of node.boards) {
          if (!VALID_BOARDS.has(board)) {
            throw new Error(`非法板块：${board}，仅支持 ${Array.from(VALID_BOARDS).join(', ')}`);
          }
        }
      }
      break;
    case 'custom_indicator':
      if (!node.scriptId || typeof node.scriptId !== 'string') {
        throw new Error('custom_indicator 节点缺少 scriptId');
      }
      if (typeof node.version !== 'number' || node.version < 1) {
        throw new Error('custom_indicator 节点 version 无效');
      }
      break;
  }
}

// ==================== 基本面检测 ====================

/** 检测 FilterNode 中是否包含高风险基本面字段 */
export function detectFundamentalFields(node: FilterNode): string[] {
  const found: string[] = [];

  function walk(n: FilterNode): void {
    switch (n.type) {
      case 'and':
      case 'or':
        for (const child of n.children) walk(child);
        break;
      case 'not':
        walk(n.child);
        break;
      case 'range':
        if (HIGH_RISK_FUNDAMENTAL_FIELDS.has(n.field)) {
          found.push(n.field);
        }
        break;
      case 'pattern':
      case 'kline':
      case 'market':
        break;
    }
  }

  walk(node);
  return found;
}

// ==================== 条件下推 ====================

/** 可提取的无歧义条件 */
export interface PushdownPredicates {
  boards?: string[];
  marketCapMin?: number;
  marketCapMax?: number;
  priceMin?: number;
  priceMax?: number;
}

/**
 * 提取可下推的无歧义条件（仅从 AND 子句中提取）
 * 嵌套在 OR/NOT 中的条件标记为"引擎侧过滤"
 *
 * P2-1.4: 当前策略保守，遇到 or/not 直接标记为 engineSideOnly。
 * 未来优化方向：
 * 1. 同字段 OR 合并：如 (pe<10) OR (pe>100) 可合并为范围并集，后端需支持
 * 2. OR 拆分为多独立查询：将 or 拆解为多个下推查询，分别拉取候选池后在前端做 union 合并
 * 3. 利用后端过滤能力减少前端计算量
 */
export function extractPushdownPredicates(node: FilterNode): {
  pushdown: PushdownPredicates;
  engineSideOnly: boolean;
} {
  const pushdown: PushdownPredicates = {};
  let engineSideOnly = false;

  function walk(n: FilterNode): void {
    switch (n.type) {
      case 'and':
        for (const child of n.children) walk(child);
        break;
      case 'or':
      case 'not':
        engineSideOnly = true;
        break;
      case 'range':
        if (n.field === 'market_cap') {
          pushdown.marketCapMin = n.min;
          pushdown.marketCapMax = n.max;
        } else if (n.field === 'close') {
          pushdown.priceMin = n.min;
          pushdown.priceMax = n.max;
        }
        break;
      case 'market':
        pushdown.boards = n.boards;
        break;
      case 'pattern':
      case 'kline':
        engineSideOnly = true;
        break;
    }
  }

  walk(node);
  return { pushdown, engineSideOnly };
}

/** 将 PushdownPredicates 转为查询字符串 */
export function pushdownToQueryString(p: PushdownPredicates): string {
  const params = new URLSearchParams();
  if (p.boards && p.boards.length > 0) {
    params.set('listed_board', p.boards.join(','));
  }
  if (p.marketCapMin !== undefined) {
    params.set('market_cap_min', String(p.marketCapMin));
  }
  if (p.marketCapMax !== undefined) {
    params.set('market_cap_max', String(p.marketCapMax));
  }
  if (p.priceMin !== undefined) {
    params.set('price_min', String(p.priceMin));
  }
  if (p.priceMax !== undefined) {
    params.set('price_max', String(p.priceMax));
  }
  return params.toString();
}

// ==================== 审计日志 ====================

/** 筛选审计报告 */
export interface FilterAuditTrail {
  /** 下推至后端 API 的条件 */
  pushdownQuery: string;
  /** 引擎侧过滤前股票数量 */
  beforeEngineFilter: number;
  /** 引擎侧过滤后股票数量 */
  afterEngineFilter: number;
  /** 被剔除股票示例 */
  removedExamples: Array<{ code: string; reason: string }>;
  /** 是否包含引擎侧过滤 */
  hasEngineSideFilter: boolean;
}

// ==================== URL 参数解析 ====================

const TREE_MAX_SIZE = 2048;
const TREE_MAX_DEPTH = 10;

/** FilterNode 的标准字段集合（用于剥离非法字段） */
const FILTER_NODE_STANDARD_FIELDS = new Set([
  'type', 'children', 'child', 'field', 'min', 'max',
  'pattern', 'lookbackDays', 'boards', 'watchlistOnly',
  'scriptId', 'version',
]);

/**
 * 递归移除 FilterNode 中非标准字段（不可变操作，返回新对象）
 * 职责分层契约：tree 参数仅承载选股逻辑，不包含策略执行参数
 * @returns { strippedFields: string[] } 被移除的字段名列表（用于审计）
 */
function stripNonStandardFields(node: Record<string, unknown>): { strippedFields: string[] } {
  const strippedFields: string[] = [];

  // 只对普通对象执行遍历，跳过数组类型
  if (typeof node !== 'object' || node === null || Array.isArray(node)) {
    return { strippedFields };
  }

  for (const key of Object.keys(node)) {
    if (!FILTER_NODE_STANDARD_FIELDS.has(key)) {
      console.warn(`[FilterTree] 检测到非标准字段 "${key}"，已自动剥离（职责分层契约）`);
      delete node[key];
      strippedFields.push(key);
    }
  }
  // 递归处理子节点
  if (Array.isArray(node.children)) {
    for (const child of node.children) {
      if (typeof child === 'object' && child !== null) {
        const result = stripNonStandardFields(child as Record<string, unknown>);
        strippedFields.push(...result.strippedFields);
      }
    }
  }
  if (node.child && typeof node.child === 'object') {
    const result = stripNonStandardFields(node.child as Record<string, unknown>);
    strippedFields.push(...result.strippedFields);
  }
  return { strippedFields };
}

/**
 * 从 URL 参数解析 FilterNode
 * 安全校验：大小限制、深度限制、字段值白名单、数值范围、Schema 预检
 * 职责分层：自动剥离非标准字段（如 config/settings 等执行参数）
 * @returns 解析后的 FilterNode 及被剥离的非标准字段列表
 */
export function parseTreeParam(raw: string | null): { tree: FilterNode | null; strippedFields: string[] } {
  if (!raw) return { tree: null, strippedFields: [] };

  // 大小校验
  if (raw.length > TREE_MAX_SIZE) {
    throw new Error('选股条件过长，请简化后重试');
  }

  // Base64 解码
  const decoded = atob(raw);
  if (decoded.length > TREE_MAX_SIZE) {
    throw new Error('选股条件过长，请简化后重试');
  }

  // JSON 解析
  const parsed = JSON.parse(decoded);

  // P1-1.1: 显式校验根节点必须是对象，拒绝数组类型
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('选股条件格式错误：根节点必须是对象');
  }

  // 剥离非标准字段（执行参数过滤），收集审计日志
  const { strippedFields } = stripNonStandardFields(parsed as Record<string, unknown>);
  if (strippedFields.length > 0) {
    console.warn(`[FilterTree] 剥离了 ${strippedFields.length} 个非标准字段: ${strippedFields.join(', ')}`);
  }

  // 递归深度校验 + Schema 校验 + 字段值白名单
  validateFilterNode(parsed as FilterNode, 0, TREE_MAX_DEPTH, TREE_MAX_SIZE);

  return { tree: parsed as FilterNode, strippedFields };
}

/**
 * 将 FilterNode 序列化为 URL 参数（Base64 编码）
 * 与 parseTreeParam 对称：先 JSON.stringify 再 btoa
 */
export function encodeTreeParam(tree: FilterNode): string {
  const serialized = JSON.stringify(tree);
  if (serialized.length > TREE_MAX_SIZE) {
    throw new Error(`选股条件序列化长度超过限制 (${TREE_MAX_SIZE}字节)，请简化后重试`);
  }
  return btoa(serialized);
}