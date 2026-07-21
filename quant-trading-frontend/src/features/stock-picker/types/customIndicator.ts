/**
 * 自编指标 + 选股方案 数据模型（V1.0）
 *
 * 设计原则：
 * - 自编指标和系统预设指标共享 IndicatorSource 枚举，便于后续扩展
 * - 临时参数 (tempParams) 独立于模板默认参数 (params)，确保修改不覆盖模板
 * - 条件中携带 source + sourceId + 必要快照，方案回显时按 ID 找模板，找不到则置灰失效
 * - 公式脚本以字符串形式保存（通达信/Python Ta-Lib），不解析（V1.0 不做公式沙箱）
 */

// =====================================================================
// 1. 指标分类（PRD 3.2 表）
// =====================================================================

export type IndicatorCategory = 'trend' | 'oscillator' | 'volume_price' | 'valuation' | 'other';

export const INDICATOR_CATEGORIES: { value: IndicatorCategory; label: string; color: string }[] = [
  { value: 'trend', label: '趋势类', color: 'blue' },
  { value: 'oscillator', label: '震荡类', color: 'purple' },
  { value: 'volume_price', label: '量价类', color: 'orange' },
  { value: 'valuation', label: '估值类', color: 'green' },
  { value: 'other', label: '其他', color: 'default' },
];

export function getCategoryMeta(value: IndicatorCategory) {
  return INDICATOR_CATEGORIES.find((c) => c.value === value) ?? INDICATOR_CATEGORIES[4];
}

// =====================================================================
// 2. 运算符（PRD 3.2 表 - 8 种）
// =====================================================================

export type IndicatorOperator = '>' | '>=' | '<' | '<=' | '==' | 'range' | 'cross_up' | 'cross_down';

export const INDICATOR_OPERATORS: { value: IndicatorOperator; label: string; needsTwoValues: boolean }[] = [
  { value: '>', label: '大于 (>)', needsTwoValues: false },
  { value: '>=', label: '大于等于 (>=)', needsTwoValues: false },
  { value: '<', label: '小于 (<)', needsTwoValues: false },
  { value: '<=', label: '小于等于 (<=)', needsTwoValues: false },
  { value: '==', label: '等于 (==)', needsTwoValues: false },
  { value: 'range', label: '区间', needsTwoValues: true },
  { value: 'cross_up', label: '上穿', needsTwoValues: true },
  { value: 'cross_down', label: '下穿', needsTwoValues: true },
];

export function getOperatorMeta(value: IndicatorOperator) {
  return INDICATOR_OPERATORS.find((o) => o.value === value);
}

// =====================================================================
// 3. 可见范围（PRD 3.2 表 - V1.0 暂仅支持"仅本人"）
// =====================================================================

export type IndicatorVisibility = 'private' | 'team';

export const INDICATOR_VISIBILITY: { value: IndicatorVisibility; label: string; disabled?: boolean }[] = [
  { value: 'private', label: '仅本人可用' },
  { value: 'team', label: '团队共享（企业版专属）', disabled: true },
];

// =====================================================================
// 4. 指标参数（动态参数表单）
// =====================================================================

export interface CustomIndicatorParam {
  /** 参数名（用户在公式中引用的标识符，2-20 字符，字母数字下划线） */
  name: string;
  /** 默认值（字符串，运行时解析为 number/bool） */
  defaultValue: string;
  /** 参数说明（≤ 50 字符） */
  description: string;
}

// =====================================================================
// 5. 自编指标实体（PRD 5.2 表核心字段）
// =====================================================================

export type IndicatorSyntax = 'python_talib';

export const INDICATOR_SYNTAXES: { value: IndicatorSyntax; label: string }[] = [
  { value: 'python_talib', label: 'Python' },
];

export interface CustomIndicator {
  id: string;
  /** 用户 ID（V1.0 mock user_id，V2.0 接入后端后为真实用户） */
  userId: string;
  /** 指标名称（用户内唯一，2-30 字符） */
  name: string;
  /** 指标分类 */
  category: IndicatorCategory;
  /** 公式脚本（通达信 / Python Ta-Lib） */
  formula: string;
  /** 公式语法 */
  syntax: IndicatorSyntax;
  /** 自定义参数（动态表单） */
  params: CustomIndicatorParam[];
  /** 默认运算符 */
  operator: IndicatorOperator;
  /** 默认阈值（区间运算符时为 [low, high] 数组；上穿/下穿时为 [lineA, lineB]） */
  defaultThreshold: number | [number, number];
  /** 指标说明 */
  description: string;
  /** 可见范围 */
  visibility: IndicatorVisibility;
  /** 软删除标记 */
  deleted?: boolean;
  /** 软删除时间戳（ISO 8601）— 仅 deleted=true 时有值 */
  deletedAt?: string;
  /** 创建时间（ISO 8601） */
  createdAt: string;
  /** 更新时间（ISO 8601） */
  updatedAt: string;
}

// =====================================================================
// 6. 指标来源（系统预设 / 用户自编 - PRD 2.1）
// =====================================================================

export type IndicatorSource = 'system' | 'custom';

// =====================================================================
// 7. 选股方案（PRD 5.3/5.4 表核心字段）
// =====================================================================

export interface PlanCondition {
  id: string;
  /** 条件 ID（应用层生成） */
  /** 指标来源 */
  source: IndicatorSource;
  /** 指标 ID（系统预设填 fieldKey，如 'rsi_oversold'；自编填 CustomIndicator.id） */
  sourceId: string;
  /** 指标名称（快照，方案回显时若无模板则使用） */
  sourceName: string;
  /** 关系操作符（AND/OR/NOT）— 与 FilterCondition 一致 */
  op: 'AND' | 'OR' | 'NOT';
  /** 临时参数（本次选股覆盖模板默认参数，不写回模板） */
  tempParams: Record<string, string>;
  /** 临时阈值（覆盖 CustomIndicator.defaultThreshold） */
  tempThreshold: number | [number, number];
  /** 临时运算符（覆盖 CustomIndicator.operator） */
  tempOperator: IndicatorOperator;
  /** 是否失效（自编指标被删除时置 true） */
  invalid?: boolean;
  /** 失效原因文案 */
  invalidReason?: string;
  /** 排序序号 */
  order: number;
}

export interface ScreenerPlan {
  id: string;
  userId: string;
  name: string;
  description: string;
  conditions: PlanCondition[];
  createdAt: string;
  updatedAt: string;
  isDefault: boolean;
}

// =====================================================================
// 8. 公式语法预校验（V1.0 仅做基础非空 + 长度 + 危险字符检查）
// =====================================================================

// 允许 import 的模块白名单
const ALLOWED_IMPORT_MODULES = ['numpy', 'pandas'];

const DANGEROUS_KEYWORDS = [
  'exec', 'eval', 'os.', 'subprocess', '__', 'system', 'open(',
  'compile(', 'globals(', 'locals(', 'getattr(', 'setattr(', 'delattr(',
];

export interface FormulaValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export function validateFormula(formula: string, _syntax: IndicatorSyntax): FormulaValidation {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!formula || !formula.trim()) {
    errors.push('公式不能为空');
    return { valid: false, errors, warnings };
  }

  if (formula.length > 8000) {
    errors.push('公式长度不能超过 8000 字符');
  }

  // 括号配对检查
  const parenResult = checkParensBalance(formula);
  if (!parenResult.ok) {
    errors.push(parenResult.error!);
  }

  // 未关闭函数检测
  const funcResult = checkUnclosedFunction(formula);
  if (!funcResult.ok) {
    errors.push(funcResult.error!);
  }

  for (const kw of DANGEROUS_KEYWORDS) {
    if (formula.toLowerCase().includes(kw)) {
      errors.push(`公式包含禁止的关键字「${kw}」，请移除后重试`);
    }
  }

  // import 白名单校验：只允许 import numpy / import pandas
  const importErrors = checkImports(formula);
  errors.push(...importErrors);

  // === 新增：calculate 函数存在性与签名校验 ===
  const signatureCheck = checkCalculateSignature(formula);
  errors.push(...signatureCheck.errors);
  warnings.push(...signatureCheck.warnings);

  // === 新增：常见错误模式检测 ===
  const patternCheck = checkCommonMistakes(formula);
  errors.push(...patternCheck.errors);
  warnings.push(...patternCheck.warnings);

  return { valid: errors.length === 0, errors, warnings };
}

/**
 * 括号配对检查（P3.2 增强）
 * 扫描 ( 和 )，统计未配对数量
 * 不区分嵌套类型（通达信仅使用小括号）
 */
function checkParensBalance(formula: string): { ok: boolean; error?: string } {
  let opens = 0;
  for (let i = 0; i < formula.length; i++) {
    if (formula[i] === '(') opens++;
    else if (formula[i] === ')') {
      opens--;
      if (opens < 0) {
        return { ok: false, error: `公式第 ${i + 1} 字符")"缺少对应"("` };
      }
    }
  }
  if (opens > 0) {
    return { ok: false, error: `公式有 ${opens} 个"("未闭合` };
  }
  return { ok: true };
}

/**
 * 未关闭函数检测
 * 检查形如 IDENTIFIER( 的模式 — 如果函数名后跟 ( 但缺少对应 )，视为未关闭
 */
function checkUnclosedFunction(formula: string): { ok: boolean; error?: string } {
  // 匹配 字母数字下划线 后跟 ( 但内部 ( 数量不匹配的函数
  const funcCallRegex = /\b([A-Za-z_][A-Za-z0-9_]*)\s*\(/g;
  let match;
  while ((match = funcCallRegex.exec(formula)) !== null) {
    const startIdx = match.index + match[0].length; // ( 之后位置
    // 统计从这个 ( 到公式末尾的 ( 和 ) 数量差
    let depth = 1;
    for (let i = startIdx; i < formula.length; i++) {
      if (formula[i] === '(') depth++;
      else if (formula[i] === ')') depth--;
      if (depth === 0) break;
    }
    if (depth !== 0) {
      return { ok: false, error: `函数"${match[1]}"参数未闭合（缺少")"）` };
    }
  }
  return { ok: true };
}

/**
 * import 白名单校验
 * 只允许 import numpy / import pandas（及其别名）
 * 格式: import numpy, import numpy as np, from numpy import ..., from pandas import ...
 */
function checkImports(formula: string): string[] {
  const errors: string[] = [];
  const lower = formula.toLowerCase();

  // 1. 匹配 from ... import 语句，验证 from 的模块名
  const fromRegex = /\bfrom\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import\b/gi;
  let match;
  while ((match = fromRegex.exec(lower)) !== null) {
    const module = match[1].split('.')[0];
    if (!ALLOWED_IMPORT_MODULES.includes(module)) {
      errors.push(`不允许 from 模块「${module}」，仅支持 from numpy / from pandas`);
    }
  }

  // 2. 移除所有 from ... import ... 语句，再检查剩余的独立 import
  const stripped = lower.replace(/\bfrom\s+[a-zA-Z_][a-zA-Z0-9_.]*\s+import\b[^;\n]*/gi, '');
  const importRegex = /\bimport\s+([a-zA-Z_][a-zA-Z0-9_.]*)/gi;
  while ((match = importRegex.exec(stripped)) !== null) {
    const module = match[1].split('.')[0];
    if (!ALLOWED_IMPORT_MODULES.includes(module)) {
      errors.push(`不允许 import 模块「${module}」，仅支持 import numpy / import pandas`);
    }
  }

  return errors;
}

// =====================================================================
// 9. 参数名校验
// =====================================================================

/** 系统保留字段名，参数名不得与之冲突 */
const RESERVED_PARAM_NAMES = new Set([
  'close', 'high', 'low', 'open', 'volume',
  'n', 'stock_idx', 'np', 'result', 'results', 'calculate',
]);

export function validateParamName(name: string): string | null {
  if (!name) return '参数名不能为空';
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)) {
    return '参数名须以字母/下划线开头，只能包含字母数字下划线';
  }
  if (name.length > 20) return '参数名长度不能超过 20 字符';
  if (RESERVED_PARAM_NAMES.has(name.toLowerCase())) {
    return `参数名「${name}」为系统保留字段，请更换`;
  }
  return null;
}

// =====================================================================
// 10. 指标名称校验
// =====================================================================

export function validateIndicatorName(name: string): string | null {
  if (!name || !name.trim()) return '指标名称不能为空';
  if (name.length < 2 || name.length > 30) return '指标名称长度须为 2-30 字符';
  if (!/^[\u4e00-\u9fa5A-Za-z0-9_\-（）()]+$/.test(name)) {
    return '指标名称仅支持中英文、数字、下划线、连字符和括号';
  }
  return null;
}

// =====================================================================
// 11. JSON 导入导出 schema
// =====================================================================

export const EXPORT_FORMAT_VERSION = 1;

export interface IndicatorExportFile {
  version: number;
  exportedAt: string;
  userId: string;
  indicators: CustomIndicator[];
}

// =====================================================================
// 12. calculate 函数签名校验（V1.1 新增）
// =====================================================================

/**
 * 校验 calculate 函数的存在性和参数签名
 *
 * 系统约定：
 * - 必须定义 def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
 * - 5 个参数分别对应 开盘价、最高价、最低价、收盘价、成交量（均为一维数组）
 * - 返回值：单值（int/float）或 一维数组（长度与输入一致）
 */
function checkCalculateSignature(formula: string): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];

  // 匹配 def calculate(...) 的函数定义
  const calcRegex = /def\s+calculate\s*\(([^)]*)\)/;
  const match = formula.match(calcRegex);

  if (!match) {
    errors.push('未找到 calculate 函数定义，必须定义 def calculate(open_prices, high_prices, low_prices, close_prices, volumes):');
    return { errors, warnings };
  }

  const paramsStr = match[1].trim();
  if (!paramsStr) {
    errors.push('calculate 函数缺少参数，必须包含 5 个参数：open_prices, high_prices, low_prices, close_prices, volumes');
    return { errors, warnings };
  }

  // 拆分参数（去除默认值）
  const params = paramsStr
    .split(',')
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .map((p) => p.split('=')[0].trim().split(':')[0].trim());

  if (params.length !== 5) {
    errors.push(
      `calculate 函数参数数量不正确：期望 5 个（open_prices, high_prices, low_prices, close_prices, volumes），实际 ${params.length} 个（${params.join(', ')}）`,
    );
  }

  // 警告：参数名不规范（不强制，但给出提示）
  const expectedNames = ['open_prices', 'high_prices', 'low_prices', 'close_prices', 'volumes'];
  const lowerParams = params.map((p) => p.toLowerCase());
  const hasOpen = lowerParams.some((p) => p.includes('open'));
  const hasHigh = lowerParams.some((p) => p.includes('high'));
  const hasLow = lowerParams.some((p) => p.includes('low'));
  const hasClose = lowerParams.some((p) => p.includes('close'));
  const hasVol = lowerParams.some((p) => p.includes('vol'));

  if (!(hasOpen && hasHigh && hasLow && hasClose && hasVol)) {
    warnings.push(
      '建议 calculate 函数参数命名包含 open/high/low/close/volume 关键词，顺序为：开盘价, 最高价, 最低价, 收盘价, 成交量',
    );
  }

  return { errors, warnings };
}

// =====================================================================
// 13. 常见错误模式检测（V1.1 新增）
// =====================================================================

/**
 * 检测用户自编指标中的常见错误模式
 *
 * 主要检测：
 * 1. 二维数组使用模式（用户误以为输入是多只股票二维数组）
 * 2. 引用 stock_idx 等不存在的变量
 * 3. 其他常见陷阱
 */
function checkCommonMistakes(formula: string): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];

  // 模式 1：检测二维数组使用方式（用户误以为输入是二维的）
  // 例如：close[i], close[stock_idx], range(len(close)), for i in range(len(close))
  const twoDimPatterns = [
    {
      pattern: /\bclose\s*\[\s*(i|stock_idx|idx|index)\s*\]/,
      desc: 'close[i] / close[stock_idx] 二维数组索引',
    },
    {
      pattern: /\bopen\s*\[\s*(i|stock_idx|idx|index)\s*\]/,
      desc: 'open[i] / open[stock_idx] 二维数组索引',
    },
    {
      pattern: /\bhigh\s*\[\s*(i|stock_idx|idx|index)\s*\]/,
      desc: 'high[i] / high[stock_idx] 二维数组索引',
    },
    {
      pattern: /\blow\s*\[\s*(i|stock_idx|idx|index)\s*\]/,
      desc: 'low[i] / low[stock_idx] 二维数组索引',
    },
    {
      pattern: /\bvolume(s)?\s*\[\s*(i|stock_idx|idx|index)\s*\]/,
      desc: 'volume[i] / volumes[stock_idx] 二维数组索引',
    },
    {
      pattern: /for\s+i\s+in\s+range\s*\(\s*len\s*\(\s*(close|open|high|low|volume(s)?)\s*\)\s*\)/,
      desc: 'for i in range(len(close)) 多只股票循环模式',
    },
  ];

  for (const pat of twoDimPatterns) {
    if (pat.pattern.test(formula)) {
      warnings.push(
        `检测到疑似二维数组用法：${pat.desc}。注意：calculate 函数的输入是单只股票的一维数组，直接使用 close（整个数组）即可，不需要 close[i] 或外层循环。`,
      );
      break; // 同类警告只报一个
    }
  }

  // 模式 2：引用 stock_idx（旧版文档中用过，现已经废弃）
  if (/\bstock_idx\b/.test(formula)) {
    warnings.push(
      '检测到 stock_idx 变量。当前版本 calculate 函数只处理单只股票，不存在 stock_idx 变量，请直接使用输入数组。',
    );
  }

  // 模式 3：返回 result 列表（用户以为要返回多只股票的结果数组）
  if (/result\s*\.\s*append\s*\(/.test(formula) && /return\s+result\s*$/.test(formula)) {
    warnings.push(
      '检测到 result.append() + return result 模式。如果返回的是单只股票的每日序列（数组），这是正确的；如果是多只股票的汇总结果，则是错误的。请确认返回值含义。',
    );
  }

  // 模式 4：使用 print 但没有 import sys stdout flush（Pyodide 中 print 可能不实时显示）
  // 这只是提示，不报错

  return { errors, warnings };
}
