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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FilterGroup } from '../types'

// ============================================
// 节点类型定义（Phase 6.1.d 扁平化）
// ============================================

export type RangeOp = 'between' | 'gt' | 'lt' | 'gte' | 'lte' | 'eq'

/** 范围条件值 */
export interface RangeValue {
  min?: number
  max?: number
  /** 单值操作符（gt/lt/gte/lte/eq）时只用 min */
  op: RangeOp
}

/**
 * 平级条件（Phase 6.1.e 独立 op）
 * - field: 字段 key，如 'change_pct' / 'pattern_morning_star'
 * - fieldType: 字段类型
 * - binaryValue: binary 字段（true = 命中）
 * - rangeValue: range 字段（带操作符 + min/max）
 * - op: 该条件的关系（AND / OR / NOT），独立于其他条件
 *   - AND: 与前一个条件"且"
 *   - OR: 与前一个条件"或"
 *   - NOT: 该条件取反
 */
export interface FilterCondition {
  id: string
  field: string
  fieldType: 'range' | 'binary'
  rangeValue?: RangeValue
  binaryValue?: boolean
  /** 该条件的关系（独立） */
  op: 'AND' | 'OR' | 'NOT'
}

/**
 * 筛选树（Phase 6.1.e 扁平结构）
 * - conditions: 平级条件列表（不再嵌套子组）
 * - 无顶层 op（每个条件独立带 op）
 */
export interface FilterTree {
  conditions: FilterCondition[]
}

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

/** 创建空筛选树（无条件，默认 pendingOp=AND） */
export const createEmptyFilter = (): FilterTree => ({
  conditions: [],
})

/**
 * 创建单条条件（默认 binary 命中，op 默认 AND）
 * @param field 字段 key
 * @param op 该条件的关系（AND / OR / NOT）
 */
export const createCondition = (field: string, op: 'AND' | 'OR' | 'NOT' = 'AND'): FilterCondition => {
  const meta = FIELD_META[field]
  return {
    id: genId(),
    field,
    fieldType: meta?.type ?? 'binary',
    binaryValue: meta?.type === 'binary' ? true : undefined,
    rangeValue: meta?.type === 'range' ? { op: 'between', min: undefined, max: undefined } : undefined,
    op,
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

/** 可用的预设模板列表（Phase 6.1.e 扁平结构） */
export const PRESET_TEMPLATES: PresetTemplate[] = [
  {
    id: 'rsi_oversold',
    label: 'RSI超卖',
    description: 'RSI(6) < 30，超卖反弹信号',
    buildTree: () => ({
      conditions: [createCondition('rsi_6', 'AND')],
    }),
  },
  {
    id: 'volume_outbreak',
    label: '放量突破',
    description: '量比 > 2 + 突破20日高点',
    buildTree: () => ({
      conditions: [
        createCondition('volume_ratio', 'AND'),
        createCondition('break_high_20', 'AND'),
      ],
    }),
  },
  {
    id: 'macd_golden',
    label: 'MACD金叉',
    description: 'MACD > 0，偏多信号',
    buildTree: () => ({
      conditions: [createCondition('macd', 'AND')],
    }),
  },
  {
    id: 'volume_macd',
    label: '底部放量+MACD金叉',
    description: '量比 > 1.5 且 MACD > 0',
    buildTree: () => ({
      conditions: [
        createCondition('volume_ratio', 'AND'),
        createCondition('macd', 'AND'),
      ],
    }),
  },
  {
    id: 'consec_rise',
    label: '连续上涨',
    description: '连涨3天以上（用 consec_up_days >= 3，parquet 实际可用）',
    buildTree: () => ({
      conditions: [createCondition('consec_up_days', 'AND')],
    }),
  },
  {
    id: 'undervalued',
    label: '低估值',
    description: '市盈率 0~15',
    buildTree: () => ({
      conditions: [createCondition('pe', 'AND')],
    }),
  },
]

// ============================================
// 扁平化：FilterTree → API 参数
// ============================================

/**
 * 扁平化输出（Phase 6.1.e 独立 op）：
 * - boolFilters: binary 字段列表（实际生效 → 后端 filters 参数，逗号分隔）
 *   - AND 条件：直接传 field
 *   - OR 条件：暂用同款（后端若支持 OR 列表再调整）；前端 UI 已区分
 *   - NOT 条件：前缀 `not_` 约定；后端若不支持则只显示命中
 * - rangeFilters: 范围条件（前端预览，不传给后端）
 * - totalConditions: 条件总数
 */
export interface FlatFilters {
  boolFilters: string[]
  rangeFilters: Array<{
    field: string
    label: string
    op: RangeOp
    min?: number
    max?: number
    /** 条件关系（与 chip 前的标签一致） */
    condOp: 'AND' | 'OR' | 'NOT'
  }>
  totalConditions: number
}

/** 扁平遍历 conditions（不再递归） */
export function flattenFilters(tree: FilterTree): FlatFilters {
  const boolFilters: string[] = []
  const rangeFilters: FlatFilters['rangeFilters'] = []

  for (const cond of tree.conditions) {
    const meta = FIELD_META[cond.field]
    if (!meta) continue
    if (meta.type === 'binary' && cond.binaryValue) {
      // 命中条件：传给后端
      // - AND: `field`
      // - OR:  `or_field`（后端识别为 OR 关系）
      // - NOT: `not_field`（后端识别为 NOT 关系）
      let token = cond.field
      if (cond.op === 'NOT') token = `not_${cond.field}`
      else if (cond.op === 'OR') token = `or_${cond.field}`
      boolFilters.push(token)
    } else if (meta.type === 'range' && cond.rangeValue) {
      rangeFilters.push({
        field: cond.field,
        label: meta.label,
        op: cond.rangeValue.op,
        min: cond.rangeValue.min,
        max: cond.rangeValue.max,
        condOp: cond.op,
      })
    }
  }

  return {
    boolFilters,
    rangeFilters,
    totalConditions: tree.conditions.length,
  }
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
 * ConditionBuilder（Phase 6.1.e 独立 op + pendingOp）
 * - 不再有顶层 op（每个条件独立带 op）
 * - 三个独立按钮 [AND] [OR] [NOT]（互斥单选）
 *   - 反映"下一个待添加条件将使用的关系"（pendingOp）
 *   - 已添加条件的 op 不会被后续切换影响
 * - 选中关系 + 点击弹层中的指标 → 创建「该 op + 该指标」条件
 * - 选中后只显示指标本身（chip），不能调整参数
 */
export default function ConditionBuilder({
  tree,
  onChange,
  collapsed = false,
  onToggleCollapsed,
}: ConditionBuilderProps) {
  const flat = useMemo(() => flattenFilters(tree), [tree])
  const [addPanelOpen, setAddPanelOpen] = useState(false)
  const [pendingOp, setPendingOp] = useState<'AND' | 'OR' | 'NOT'>('AND')
  const addBtnRef = useRef<HTMLButtonElement>(null)
  const addPanelRef = useRef<HTMLDivElement>(null)
  const [addPanelPos, setAddPanelPos] = useState<{ top: number; left: number } | null>(null)

  // 「重置」按钮：清空条件树 + pendingOp 回到 AND
  const handleReset = useCallback(() => {
    onChange(createEmptyFilter())
    setPendingOp("AND")
  }, [onChange])

  // 应用预设模板
  const handleApplyPreset = useCallback(
    (template: PresetTemplate) => {
      onChange(template.buildTree())
    },
    [onChange]
  )

  // 添加条件（使用当前 pendingOp）
  const handleAddCondition = useCallback(
    (fieldKey: string) => {
      onChange({
        ...tree,
        conditions: [...tree.conditions, createCondition(fieldKey, pendingOp)],
      })
      setAddPanelOpen(false)
    },
    [tree, onChange, pendingOp]
  )

  // 切换某条件的 op（点击 op 标签时切换 AND/OR/NOT 循环）
  const cycleOp = useCallback(
    (id: string) => {
      const next: Record<'AND' | 'OR' | 'NOT', 'AND' | 'OR' | 'NOT'> = {
        AND: 'OR',
        OR: 'NOT',
        NOT: 'AND',
      }
      onChange({
        ...tree,
        conditions: tree.conditions.map((c) =>
          c.id === id ? { ...c, op: next[c.op] } : c
        ),
      })
    },
    [tree, onChange]
  )

  // 删除条件
  const removeCondition = useCallback(
    (id: string) => {
      onChange({
        ...tree,
        conditions: tree.conditions.filter((c) => c.id !== id),
      })
    },
    [tree, onChange]
  )

  // 打开/关闭弹层
  const toggleAddPanel = useCallback(() => {
    if (!addPanelOpen && addBtnRef.current) {
      const r = addBtnRef.current.getBoundingClientRect()
      // 弹层展开在按钮上方（避免被侧边栏底部裁剪）
      setAddPanelPos({ top: r.top - 8, left: r.left })
    }
    setAddPanelOpen((v) => !v)
  }, [addPanelOpen])

  // 点击外部关闭弹层
  useEffect(() => {
    if (!addPanelOpen) return
    const handler = (e: MouseEvent) => {
      if (
        addPanelRef.current &&
        !addPanelRef.current.contains(e.target as Node) &&
        addBtnRef.current &&
        !addBtnRef.current.contains(e.target as Node)
      ) {
        setAddPanelOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [addPanelOpen])

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
        <div className="p-3 border-t border-border-color space-y-2">
          {/* 预设模板按钮行（Phase 6.1.b） */}
          <div
            className="flex items-center gap-2 flex-wrap"
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

          {/* 三个独立按钮：AND / OR / NOT（互斥单选）— 控制"下一个待添加条件"的关系 */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-text-muted text-xs">关系:</span>
            <div
              className="inline-flex bg-bg-card border border-border-color rounded overflow-hidden"
              data-testid="pending-op-toggle"
            >
              {(['AND', 'OR', 'NOT'] as const).map((op) => {
                const active = pendingOp === op
                const activeClass =
                  op === "AND"
                    ? "bg-up-green text-white"
                    : op === "OR"
                      ? "bg-blue-500 text-white"
                      : "bg-yellow-500 text-white"
                return (
                  <button
                    key={op}
                    onClick={() => setPendingOp(op)}
                    className={`text-xs px-3 py-1 ${
                      active
                        ? activeClass
                        : "text-text-secondary hover:bg-bg-primary"
                    }`}
                    data-testid={`pending-op-${op}`}
                  >
                    {op}
                  </button>
                )
              })}
            </div>
            <span className="text-text-muted text-xs">
              {pendingOp === 'AND' ? '（且）' : pendingOp === 'OR' ? '（或）' : '（取反）'}
            </span>

            <span className="text-text-muted/40">|</span>

            <button
              ref={addBtnRef}
              onClick={toggleAddPanel}
              className={`text-xs px-2 py-1 rounded ${
                addPanelOpen
                  ? "bg-up-green/20 text-up-green border border-up-green/40"
                  : "text-text-muted hover:text-up-green border border-border-color"
              }`}
              data-testid="add-condition-0"
            >
              + 条件
            </button>
          </div>

          {/* 条件列表（平级） */}
          {tree.conditions.length === 0 ? (
            <div className="text-text-muted text-xs italic py-1.5 px-1">— 暂无条件，点击"+ 条件"添加 —</div>
          ) : (
            <div className="flex flex-wrap gap-1.5" data-testid="condition-list">
              {tree.conditions.map((cond) => (
                <ConditionRow
                  key={cond.id}
                  condition={cond}
                  onCycleOp={() => cycleOp(cond.id)}
                  onRemove={() => removeCondition(cond.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* 「+ 条件」弹层（fixed 定位，避免被侧边栏滚动容器裁剪） */}
      {addPanelOpen && addPanelPos && (
        <div
          ref={addPanelRef}
          className="fixed z-50 w-56 bg-bg-card border border-border-color rounded shadow-xl py-1 max-h-80 overflow-y-auto"
          style={{
            // 弹层展开在按钮左侧（避免超出视口右/底）
            top: Math.max(8, addPanelPos.top - 320),
            left: Math.max(8, addPanelPos.left - 224),
          }}
          data-testid="add-condition-panel"
        >
          {(['pattern', 'breakout', 'consecutive'] as const).map((gid) => {
            const groupMeta = FIELD_GROUPS.find((g) => g.id === gid)
            if (!groupMeta) return null
            return (
              <div key={gid} className="border-b border-border-color/40 last:border-b-0">
                <div
                  className="px-3 py-1 text-xs text-text-muted font-medium bg-bg-secondary/60"
                  data-testid={`add-condition-panel-${gid}-header`}
                >
                  {groupMeta.label}
                </div>
                {groupMeta.fieldKeys.map((fk) => (
                  <button
                    key={fk}
                    onClick={() => handleAddCondition(fk)}
                    className="block w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-bg-primary"
                    data-testid={`add-condition-panel-${gid}-${fk}`}
                  >
                    {FIELD_META[fk]?.label ?? fk}
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ============================================
// ConditionRow：单条件 chip（op 标签 + 指标 + 删除）
// ============================================

interface ConditionRowProps {
  condition: FilterCondition
  /** 点击 op 标签时循环切换 AND → OR → NOT */
  onCycleOp: () => void
  onRemove: () => void
}

/**
 * ConditionRow：单条件展示（Phase 6.1.e 独立 op + chip 只读）
 * - 关系标签：chip 前的 [AND] / [OR] / [NOT]（取自 condition.op）
 *   - 点击 op 标签可循环切换 AND → OR → NOT → AND
 * - 指标本身：chip 主体（只读，参数调整在条件树/弹层中完成）
 * - 删除：右侧 ×
 *
 * 三个 op 的颜色：
 *   - AND：绿色
 *   - OR：蓝色
 *   - NOT：黄色
 */
function ConditionRow({ condition, onCycleOp, onRemove }: ConditionRowProps) {
  const meta = FIELD_META[condition.field]
  const label = meta?.label ?? condition.field

  // 关系标签颜色（按 condition.op 决定）
  const opClass =
    condition.op === "AND"
      ? "bg-up-green/15 text-up-green border-up-green/30"
      : condition.op === "OR"
        ? "bg-blue-500/15 text-blue-400 border-blue-500/30"
        : "bg-yellow-500/15 text-yellow-400 border-yellow-500/30"

  return (
    <div
      className="inline-flex items-center gap-1 text-xs"
      data-testid={`condition-row-wrap-${condition.id}`}
    >
      {/* 关系标签（可点击循环切换） */}
      <button
        onClick={onCycleOp}
        className={`px-1.5 py-0.5 rounded border text-[10px] font-bold cursor-pointer hover:opacity-80 transition-opacity ${opClass}`}
        title={`点击切换关系（当前：${condition.op}，下一档：${condition.op === "AND" ? "OR" : condition.op === "OR" ? "NOT" : "AND"}）`}
        data-testid={`condition-row-op-${condition.id}`}
        data-op={condition.op}
      >
        {condition.op}
      </button>

      {/* 指标 chip（只读） */}
      <span
        className="inline-flex items-center gap-1 border pl-1.5 pr-1 py-0.5 rounded bg-bg-card border-border-color text-text-primary"
        data-testid={`condition-row-${condition.id}`}
        data-field={condition.field}
        data-op={condition.op}
      >
        <span className="text-xs">✓</span>
        <span className="font-medium">{label}</span>
      </span>

      {/* 删除按钮 */}
      <button
        onClick={onRemove}
        className="text-text-muted hover:text-down-red px-1"
        title="删除该条件"
        data-testid={`condition-row-remove-${condition.id}`}
      >
        ×
      </button>
    </div>
  )
}
