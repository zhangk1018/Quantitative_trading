/**
 * ConditionBuilder.tsx - 条件组合面板（搭积木式 AND/OR/NOT 逻辑筛选 UI）
 *
 * Phase 6.1.a (2026-06-10)
 * - 递归条件树：group(AND/OR/NOT) + condition(范围/二值/选择)
 * - 字段从 fetchMeta 动态加载（get_filter_meta 接口）
 * - 扁平化输出为 ApiRequest 所需的 filters/industry/listed_board 格式
 * - 后端只支持 bool filters（逗号分隔），range 条件前端预览，标注"前端筛选"
 *
 * 设计取舍：
 * - 条件嵌套用 group + 简单操作符（AND/OR/NOT），避免过度复杂
 * - 范围条件用 { min, max } 数字输入；二值条件用「是/否」select
 * - 删除按钮 + 添加子条件/子组
 */

import { useCallback, useMemo } from 'react'
import type { FilterGroup } from '../types'

// ============================================
// 节点类型定义
// ============================================

/** 范围操作符 */
export type RangeOp = 'between' | 'gt' | 'lt' | 'gte' | 'lte' | 'eq'

/** 范围条件值 */
export interface RangeValue {
  min?: number
  max?: number
  /** 单值操作符（gt/lt/gte/lte/eq）时只用 min */
  op: RangeOp
}

/** 条件节点 */
export interface ConditionNode {
  id: string
  type: 'condition'
  field: string                  // 字段 key，如 'change_pct' / 'pattern_morning_star'
  fieldType: 'range' | 'binary'  // 字段类型
  // range 字段
  rangeValue?: RangeValue
  // binary 字段（true = 命中，false = 未命中）
  binaryValue?: boolean
}

/** 组节点（AND/OR/NOT） */
export interface GroupNode {
  id: string
  type: 'group'
  op: 'AND' | 'OR' | 'NOT'
  children: (ConditionNode | GroupNode)[]
}

/** 根节点永远是一个 group（AND） */
export type FilterTree = GroupNode

// ============================================
// 字段元数据（与 ScreenerService.filter_config 对齐）
// ============================================

/**
 * 字段元数据（按 group 分类）
 * 与 backend/core/service/screener_service.py:_init_filter_config 镜像
 * 后续可改为 fetchMeta.get_filter_meta 动态加载
 */
export const FIELD_META: Record<string, { label: string; type: 'range' | 'binary'; unit?: string }> = {
  // 价格
  close: { label: '收盘价', type: 'range', unit: '元' },
  change: { label: '涨跌额', type: 'range', unit: '元' },
  change_pct: { label: '涨跌幅', type: 'range', unit: '%' },
  high: { label: '最高价', type: 'range', unit: '元' },
  low: { label: '最低价', type: 'range', unit: '元' },
  open: { label: '开盘价', type: 'range', unit: '元' },
  pre_close: { label: '前收盘价', type: 'range', unit: '元' },
  // 成交量
  volume: { label: '成交量', type: 'range', unit: '手' },
  amount: { label: '成交额', type: 'range', unit: '万元' },
  turnover_rate: { label: '换手率', type: 'range', unit: '%' },
  volume_ratio: { label: '量比', type: 'range' },
  vol_ratio_5: { label: '5日量比', type: 'range' },
  // 技术指标
  rsi_6: { label: 'RSI(6)', type: 'range' },
  rsi_12: { label: 'RSI(12)', type: 'range' },
  rsi_24: { label: 'RSI(24)', type: 'range' },
  macd: { label: 'MACD', type: 'range' },
  boll_upper: { label: '布林上轨', type: 'range', unit: '元' },
  boll_mid: { label: '布林中轨', type: 'range', unit: '元' },
  boll_lower: { label: '布林下轨', type: 'range', unit: '元' },
  kdj_k: { label: 'KDJ-K', type: 'range' },
  kdj_d: { label: 'KDJ-D', type: 'range' },
  kdj_j: { label: 'KDJ-J', type: 'range' },
  cci: { label: 'CCI', type: 'range' },
  // 基本面
  pe: { label: '市盈率(静)', type: 'range' },
  pe_ttm: { label: '市盈率(TTM)', type: 'range' },
  pb: { label: '市净率', type: 'range' },
  ps: { label: '市销率(静)', type: 'range' },
  ps_ttm: { label: '市销率(TTM)', type: 'range' },
  dv_ratio: { label: '股息率(静)', type: 'range', unit: '%' },
  dv_ttm: { label: '股息率(TTM)', type: 'range', unit: '%' },
  market_cap: { label: '总市值', type: 'range', unit: '万元' },
  circ_mv: { label: '流通市值', type: 'range', unit: '万元' },
  float_share: { label: '流通股', type: 'range', unit: '万股' },
  total_share: { label: '总股本', type: 'range', unit: '万股' },
  // 资金流向
  net_mf_amount: { label: '净流入额', type: 'range', unit: '万元' },
  net_mf_vol: { label: '净流入量', type: 'range', unit: '手' },
  // 形态识别（binary）
  pattern_hammer: { label: '锤子线', type: 'binary' },
  pattern_inv_hammer: { label: '倒锤子线', type: 'binary' },
  pattern_doji: { label: '十字星', type: 'binary' },
  pattern_bullish_engulfing: { label: '看涨吞没', type: 'binary' },
  pattern_bearish_engulfing: { label: '看跌吞没', type: 'binary' },
  pattern_morning_star: { label: '早晨之星', type: 'binary' },
  pattern_evening_star: { label: '黄昏之星', type: 'binary' },
  pattern_shooting_star: { label: '射击之星', type: 'binary' },
  pattern_hanging_man: { label: '上吊线', type: 'binary' },
  pattern_spinning_top: { label: '纺锤线', type: 'binary' },
  // 突破信号（binary）
  break_high_20: { label: '突破20日高点', type: 'binary' },
  break_high_60: { label: '突破60日高点', type: 'binary' },
  break_high_120: { label: '突破120日高点', type: 'binary' },
  break_high_250: { label: '突破250日高点', type: 'binary' },
  // 连续走势
  consec_up_3: { label: '连涨3天', type: 'binary' },
  consec_up_5: { label: '连涨5天', type: 'binary' },
  consec_up_days: { label: '连涨天数', type: 'range', unit: '天' },
}

/** 按分组组织的字段列表（用于下拉选择） */
export const FIELD_GROUPS: { id: string; label: string; fieldKeys: string[] }[] = [
  { id: 'price', label: '价格', fieldKeys: ['close', 'change', 'change_pct', 'high', 'low', 'open', 'pre_close'] },
  { id: 'volume', label: '成交量', fieldKeys: ['volume', 'amount', 'turnover_rate', 'volume_ratio', 'vol_ratio_5'] },
  { id: 'technical', label: '技术指标', fieldKeys: ['rsi_6', 'rsi_12', 'rsi_24', 'macd', 'boll_upper', 'boll_mid', 'boll_lower', 'kdj_k', 'kdj_d', 'kdj_j', 'cci'] },
  { id: 'fundamental', label: '基本面', fieldKeys: ['pe', 'pe_ttm', 'pb', 'ps', 'ps_ttm', 'dv_ratio', 'dv_ttm', 'market_cap', 'circ_mv', 'float_share', 'total_share'] },
  { id: 'fund_flow', label: '资金流向', fieldKeys: ['net_mf_amount', 'net_mf_vol'] },
  { id: 'pattern', label: '形态识别', fieldKeys: ['pattern_hammer', 'pattern_inv_hammer', 'pattern_doji', 'pattern_bullish_engulfing', 'pattern_bearish_engulfing', 'pattern_morning_star', 'pattern_evening_star', 'pattern_shooting_star', 'pattern_hanging_man', 'pattern_spinning_top'] },
  { id: 'breakout', label: '突破信号', fieldKeys: ['break_high_20', 'break_high_60', 'break_high_120', 'break_high_250'] },
  { id: 'consecutive', label: '连续走势', fieldKeys: ['consec_up_3', 'consec_up_5', 'consec_up_days'] },
]

// ============================================
// 工具函数
// ============================================

/** 生成简单 ID（前端唯一） */
let _idCounter = 0
export const genId = (): string => {
  _idCounter += 1
  return `node-${Date.now().toString(36)}-${_idCounter}`
}

/** 创建空的条件节点 */
export const createCondition = (): ConditionNode => {
  // 默认第一个 range 字段
  const firstRangeField = Object.entries(FIELD_META).find(([, m]) => m.type === 'range')?.[0] ?? 'change_pct'
  return {
    id: genId(),
    type: 'condition',
    field: firstRangeField,
    fieldType: 'range',
    rangeValue: { min: undefined, max: undefined, op: 'between' },
  }
}

/** 创建空的二进制条件节点 */
export const createBinaryCondition = (): ConditionNode => {
  return {
    id: genId(),
    type: 'condition',
    field: 'pattern_morning_star',
    fieldType: 'binary',
    binaryValue: true,
  }
}

/** 创建空的组节点 */
export const createGroup = (op: 'AND' | 'OR' | 'NOT' = 'AND'): GroupNode => {
  return {
    id: genId(),
    type: 'group',
    op,
    children: [],
  }
}

// ============================================
// 条件预设模板（Phase 6.1.b）
// ============================================

/** 预设模板定义 */
export interface PresetTemplate {
  id: string
  label: string
  description: string
  /** 构建条件树 */
  buildTree: () => FilterTree
}

/** 可用的预设模板列表 */
export const PRESET_TEMPLATES: PresetTemplate[] = [
  {
    id: 'rsi_oversold',
    label: 'RSI超卖',
    description: 'RSI(6) < 30，超卖反弹信号',
    buildTree: () => ({
      id: genId(),
      type: 'group',
      op: 'AND',
      children: [
        { id: genId(), type: 'condition', field: 'rsi_6', fieldType: 'range', rangeValue: { op: 'lt', min: 30 } },
      ],
    }),
  },
  {
    id: 'volume_outbreak',
    label: '放量突破',
    description: '量比 > 2 + 突破20日高点',
    buildTree: () => ({
      id: genId(),
      type: 'group',
      op: 'AND',
      children: [
        { id: genId(), type: 'condition', field: 'volume_ratio', fieldType: 'range', rangeValue: { op: 'gt', min: 2 } },
        { id: genId(), type: 'condition', field: 'break_high_20', fieldType: 'binary', binaryValue: true },
      ],
    }),
  },
  {
    id: 'macd_golden',
    label: 'MACD金叉',
    description: 'MACD > 0，偏多信号',
    buildTree: () => ({
      id: genId(),
      type: 'group',
      op: 'AND',
      children: [
        { id: genId(), type: 'condition', field: 'macd', fieldType: 'range', rangeValue: { op: 'gt', min: 0 } },
      ],
    }),
  },
  {
    id: 'volume_macd',
    label: '底部放量+MACD金叉',
    description: '量比 > 1.5 且 MACD > 0',
    buildTree: () => ({
      id: genId(),
      type: 'group',
      op: 'AND',
      children: [
        { id: genId(), type: 'condition', field: 'volume_ratio', fieldType: 'range', rangeValue: { op: 'gt', min: 1.5 } },
        { id: genId(), type: 'condition', field: 'macd', fieldType: 'range', rangeValue: { op: 'gt', min: 0 } },
      ],
    }),
  },
  {
    id: 'consec_rise',
    label: '连续上涨',
    description: '连涨3天以上（用 consec_up_days >= 3，parquet 实际可用）',
    buildTree: () => ({
      id: genId(),
      type: 'group',
      op: 'AND',
      children: [
        { id: genId(), type: 'condition', field: 'consec_up_days', fieldType: 'range', rangeValue: { op: 'gte', min: 3 } },
      ],
    }),
  },
  {
    id: 'undervalued',
    label: '低估值',
    description: '市盈率 0~15',
    buildTree: () => ({
      id: genId(),
      type: 'group',
      op: 'AND',
      children: [
        { id: genId(), type: 'condition', field: 'pe', fieldType: 'range', rangeValue: { op: 'between', min: 0, max: 15 } },
      ],
    }),
  },
]

// ============================================
// 扁平化：FilterTree → API 参数
// ============================================

/**
 * 扁平化输出：
 * - boolFilters: 逗号分隔的 binary 字段（实际生效 → 后端 filters 参数）
 * - rangeFilters: 范围条件（前端预览，不传给后端）
 * - 后续 Phase 6.1.b：后端支持 range 过滤时把 rangeFilters 也发出
 */
export interface FlatFilters {
  boolFilters: string[]        // 实际传给后端（binary 字段）
  rangeFilters: Array<{         // 前端预览用（后端未支持前不传）
    field: string
    label: string
    op: RangeOp
    min?: number
    max?: number
  }>
  totalConditions: number
}

/** 递归扁平化条件树（仅 binary 生效，range 记录） */
export function flattenFilters(tree: FilterTree): FlatFilters {
  const boolFilters: string[] = []
  const rangeFilters: FlatFilters['rangeFilters'] = []
  let totalConditions = 0

  const walk = (node: ConditionNode | GroupNode, _opContext: 'AND' | 'OR' | 'NOT') => {
    if (node.type === 'condition') {
      totalConditions += 1
      const meta = FIELD_META[node.field]
      if (!meta) return
      if (meta.type === 'binary' && node.binaryValue) {
        // 二值条件：仅在 AND 或裸置时有效
        // 简化处理：所有 binary 一律 AND 关系，统一传给后端
        boolFilters.push(node.field)
      } else if (meta.type === 'range' && node.rangeValue) {
        rangeFilters.push({
          field: node.field,
          label: meta.label,
          op: node.rangeValue.op,
          min: node.rangeValue.min,
          max: node.rangeValue.max,
        })
      }
    } else {
      // 递归到子节点
      node.children.forEach((child) => walk(child, node.op))
    }
  }

  walk(tree, tree.op)
  return { boolFilters, rangeFilters, totalConditions }
}

// ============================================
// 组件
// ============================================

interface ConditionBuilderProps {
  /** 当前筛选树（受控） */
  tree: FilterTree
  /** 树变更回调 */
  onChange: (tree: FilterTree) => void
  /** 折叠态（默认展开） */
  collapsed?: boolean
  onToggleCollapsed?: () => void
  /** meta 字段（预留从 fetchMeta 加载） */
  fieldMeta?: FilterGroup[] | null
}

/**
 * 条件构建器
 * 顶级根：永远是一个 AND 组；用户可嵌套 AND/OR/NOT 子组
 * Phase 6.1.d：移除「应用筛选」按钮与「实时命中数」— 由侧边栏底部「开始选股」统一触发查询
 */
export default function ConditionBuilder({
  tree,
  onChange,
  collapsed = false,
  onToggleCollapsed,
}: ConditionBuilderProps) {
  const flat = useMemo(() => flattenFilters(tree), [tree])

  // 顶层 group 变更
  const updateRoot = useCallback(
    (newRoot: FilterTree) => onChange(newRoot),
    [onChange]
  )

  // 「重置」按钮：清空条件树（恢复为空 AND 组）
  const handleReset = useCallback(() => {
    onChange(createGroup("AND"))
  }, [onChange])

  // 应用预设模板（Phase 6.1.b）
  // 预设点击后只更新条件树，不自动触发查询 — 由「开始选股」按钮统一触发
  const handleApplyPreset = useCallback(
    (template: PresetTemplate) => {
      onChange(template.buildTree())
    },
    [onChange]
  )

  return (
    <div className="border border-border-color bg-bg-secondary rounded" data-testid="condition-builder">
      {/* 标题栏 — 保留「重置」按钮（清空条件树），删除「应用筛选」和「命中 N 只」 */}
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-bg-card transition-colors"
        onClick={onToggleCollapsed}
      >
        <div className="flex items-center gap-2">
          <span className="text-text-primary text-sm font-medium">🧩 条件构建器</span>
          <span className="text-text-muted text-xs">
            {flat.totalConditions} 个条件
            {flat.boolFilters.length > 0 && ` · 后端筛选 ${flat.boolFilters.length}`}
          </span>
        </div>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={handleReset}
            className="bg-bg-card border border-border-color text-text-secondary text-xs px-2 py-1 rounded hover:bg-bg-primary"
            data-testid="condition-reset"
          >
            重置
          </button>
          <span className="text-text-muted text-xs">{collapsed ? '▶' : '▼'}</span>
        </div>
      </div>

      {/* 主体（折叠时隐藏） */}
      {!collapsed && (
        <div className="p-3 border-t border-border-color">
          {/* 预设模板按钮行（Phase 6.1.b） */}
          <div
            className="flex items-center gap-2 mb-3 flex-wrap"
            data-testid="condition-presets"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="text-text-muted text-xs">📋 预设:</span>
            {PRESET_TEMPLATES.map((t) => (
              <button
                key={t.id}
                onClick={() => handleApplyPreset(t)}
                title={t.description}
                className="bg-bg-card border border-border-color text-text-primary text-xs px-2.5 py-1 rounded hover:border-up-green hover:text-up-green transition-colors"
                data-testid={`preset-${t.id}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <GroupEditor
            group={tree}
            depth={0}
            onChange={updateRoot}
          />
        </div>
      )}
    </div>
  )
}

// ============================================
// GroupEditor：递归编辑组（AND/OR/NOT）
// ============================================

interface GroupEditorProps {
  group: GroupNode
  depth: number
  onChange: (newGroup: GroupNode) => void
}

function GroupEditor({ group, depth, onChange }: GroupEditorProps) {
  /** 更新组本身 */
  const updateSelf = (patch: Partial<GroupNode>) => {
    onChange({ ...group, ...patch })
  }

  /** 更新子节点 */
  const updateChild = (idx: number, newChild: ConditionNode | GroupNode) => {
    const newChildren = [...group.children]
    newChildren[idx] = newChild
    updateSelf({ children: newChildren })
  }

  /** 删除子节点 */
  const removeChild = (idx: number) => {
    const newChildren = group.children.filter((_, i) => i !== idx)
    updateSelf({ children: newChildren })
  }

  /**
   * 添加条件（按"具体字段"插入：形态识别/突破信号/连续走势分类下的某个指标）
   * 选中后只读 chip，不能调整参数
   */
  const addCondition = (fieldKey: string) => {
    const meta = FIELD_META[fieldKey]
    if (!meta) return
    updateSelf({
      children: [
        ...group.children,
        {
          id: genId(),
          type: 'condition',
          field: fieldKey,
          fieldType: meta.type,
          // binary 条件默认命中；range 条件不设值（chip 不显示参数）
          binaryValue: meta.type === 'binary' ? true : undefined,
          rangeValue: meta.type === 'range' ? { op: 'between', min: undefined, max: undefined } : undefined,
        },
      ],
    })
  }

  /** 添加子组 */
  const addSubgroup = (op: 'AND' | 'OR' | 'NOT') => {
    updateSelf({ children: [...group.children, createGroup(op)] })
  }

  const indent = depth * 16

  return (
    <div
      className={`relative ${depth > 0 ? 'border-l-2 border-border-color/60 pl-3 ml-2' : ''}`}
      style={{ marginLeft: depth > 0 ? `${indent}px` : 0 }}
    >
      {/* 组头：操作符 + 工具 */}
      <div className="flex items-center gap-2 mb-2">
        <select
          value={group.op}
          onChange={(e) => updateSelf({ op: e.target.value as 'AND' | 'OR' | 'NOT' })}
          className={`text-xs px-2 py-1 rounded font-medium ${
            group.op === 'AND'
              ? 'bg-up-green/20 text-up-green border border-up-green/40'
              : group.op === 'OR'
                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                : 'bg-down-red/20 text-down-red border border-down-red/40'
          }`}
          data-testid={`group-op-${depth}`}
        >
          <option value="AND">且 (AND)</option>
          <option value="OR">或 (OR)</option>
          <option value="NOT">非 (NOT)</option>
        </select>
        <span className="text-text-muted text-xs">
          {group.op === 'AND' ? '全部满足' : group.op === 'OR' ? '任一满足' : '取反'}
        </span>

        <div className="flex-1" />

        <div className="flex items-center gap-1">
          {/* 「+ 条件」按钮：hover 弹出二级菜单（3 分类 + 各自指标） */}
          <div className="relative group">
            <button
              className="text-text-muted hover:text-up-green text-xs"
              title="添加条件"
              data-testid={`add-condition-${depth}`}
            >
              + 条件
            </button>
            <div
              className="absolute z-20 top-full right-0 mt-1 w-56 bg-bg-card border border-border-color rounded shadow-lg py-1 invisible group-hover:visible hover:visible max-h-80 overflow-y-auto"
            >
              {(['pattern', 'breakout', 'consecutive'] as const).map((gid) => {
                const groupMeta = FIELD_GROUPS.find((g) => g.id === gid)
                if (!groupMeta) return null
                return (
                  <div key={gid} className="border-b border-border-color/40 last:border-b-0">
                    <div
                      className="px-3 py-1 text-xs text-text-muted font-medium bg-bg-secondary/60"
                      data-testid={`add-condition-${depth}-${gid}-header`}
                    >
                      {groupMeta.label}
                    </div>
                    {groupMeta.fieldKeys.map((fk) => (
                      <button
                        key={fk}
                        onClick={() => addCondition(fk)}
                        className="block w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-bg-primary"
                        data-testid={`add-condition-${depth}-${gid}-${fk}`}
                      >
                        {FIELD_META[fk]?.label ?? fk}
                      </button>
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
          <span className="text-text-muted/40">|</span>
          <button
            onClick={() => addSubgroup('AND')}
            className="text-text-muted hover:text-blue-400 text-xs"
            title="添加子组 (AND)"
          >
            + 子组
          </button>
        </div>
      </div>

      {/* 子节点列表 */}
      {group.children.length === 0 ? (
        <div className="text-text-muted text-xs italic py-2 px-3">— 暂无条件，点击上方按钮添加 —</div>
      ) : (
        <div className="space-y-1.5">
          {group.children.map((child, idx) => (
            <div key={child.id} className="flex items-start gap-1.5">
              <span className="text-text-muted/60 text-xs mt-2 w-6 text-right font-mono">
                {idx + 1}.
              </span>
              <div className="flex-1">
                {child.type === 'group' ? (
                  <GroupEditor
                    group={child}
                    depth={depth + 1}
                    onChange={(g) => updateChild(idx, g)}
                  />
                ) : (
                  <ConditionRow
                    condition={child}
                    onChange={(c) => updateChild(idx, c)}
                  />
                )}
              </div>
              <button
                onClick={() => removeChild(idx)}
                className="text-text-muted hover:text-down-red text-sm px-1 mt-1"
                title="删除"
                data-testid={`remove-${depth}-${idx}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================
// ConditionRow：单条件编辑（字段 + 操作符 + 值）
// ============================================

interface ConditionRowProps {
  condition: ConditionNode
  onChange: (c: ConditionNode) => void
}

/**
 * ConditionRow：单条件展示（只读 chip）
 * - 选中后只显示"指标本身"（FIELD_META.label），不再提供参数调整
 * - 不可编辑（用户新需求）：删除 select / 操作符 / 数值输入
 * - 删除仍由父级 GroupEditor 的 × 按钮控制
 */
function ConditionRow({ condition, onChange: _onChange }: ConditionRowProps) {
  const meta = FIELD_META[condition.field]
  const label = meta?.label ?? condition.field

  return (
    <div
      className="inline-flex items-center gap-1.5 bg-up-green/10 border border-up-green/30 text-up-green text-xs px-2.5 py-1 rounded"
      data-testid={`condition-row-${condition.id}`}
      data-field={condition.field}
    >
      <span className="text-xs">✓</span>
      <span className="font-medium">{label}</span>
    </div>
  )
}
