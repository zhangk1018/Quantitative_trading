import { useEffect, useState, useCallback, useMemo } from 'react'
import { fetchMeta, fetchStocks, type StockListResponse } from './api'
import type { MetaResponseData, StockResponse, ApiResponse, FilterGroup } from './types'
import StatusBar from './components/StatusBar'
import FilterPanel from './components/FilterPanel'
import StockTable from './components/StockTable'
import { KLineChart } from './components/KLineChart'
import { useKLineData } from './hooks/useKLineData'
import { useBatchKLine } from './hooks/useBatchKLine'
import { PATTERN_KEYS, type PatternKey } from './utils/patternDetector'

/** 每页显示的股票数量（符合 ≤200 的要求） */
const LIMIT = 100

/**
 * 前端需要隐藏的字段 key 集合（后端元数据中保留但前端不展示）
 * - 这些字段可能数据缺失、胜率低、或暂未实现
 */
const HIDDEN_FIELD_KEYS: ReadonlySet<string> = new Set([
  // 形态识别 - 胜率未达 Top5（红框标注）
  'pattern_inv_hammer',     // 倒锤子线
  'pattern_doji',           // 十字星
  'pattern_shooting_star',  // 射击之星
  'pattern_hanging_man',    // 上吊线
  'pattern_spinning_top',   // 纺锤线
  // 突破信号 - 数据缺失（红框标注）
  'break_high_120',         // 突破120日高点
  'break_high_250',         // 突破250日高点
  // 连续走势 - 未实现（红框标注）
  'consec_up_days',         // 连涨天数
])

/** 过滤掉需要隐藏的字段，返回新的 groups */
function filterMetaGroups(meta: MetaResponseData): MetaResponseData {
  return {
    ...meta,
    groups: meta.groups.map(g => ({
      ...g,
      fields: g.fields.filter((f: { key: string }) => !HIDDEN_FIELD_KEYS.has(f.key)),
    })),
  }
}

/**
 * 主应用组件
 * 
 * 功能：
 * 1. 整合 StatusBar（状态栏）、FilterPanel（筛选面板）、StockTable（股票表格）
 * 2. 管理筛选、排序、分页状态
 * 3. 自动加载元数据和股票列表
 * 4. 处理并发请求（取消过期请求）
 * 5. 显示加载状态和错误信息
 * 
 * 状态流转：
 * 用户操作 → 更新状态 → useEffect 触发 → 调用 API → 更新数据 → 重新渲染
 */
export default function App() {
  // ========== 数据状态 ==========
  /** 元数据（交易日、筛选选项等） */
  const [meta, setMeta] = useState<MetaResponseData | null>(null)
  /** 股票列表数据 */
  const [stocks, setStocks] = useState<StockResponse[] | null>(null)
  /** 总记录数 */
  const [total, setTotal] = useState<number>(0)
  /** 加载状态 */
  const [loading, setLoading] = useState(false)
  /** 错误信息 */
  const [error, setError] = useState<string | null>(null)

  // ========== K线图表状态 ==========
  const [showKLine, setShowKLine] = useState(false)
  const {
    data: klineData,
    loading: klineLoading,
    error: klineError,
    stockCode: klineStockCode,
    fetchData: fetchKLineData,
    clearData: clearKLineData
  } = useKLineData()

  // ========== 形态识别 - 批量 K线（含 localStorage 缓存） ==========
  const {
    patterns: patternResults,
    loading: batchKLineLoading,
    progress: batchKLineProgress,
    patternCacheHits,
    klineCacheHits,
    fetchBatch: fetchBatchKLine
  } = useBatchKLine()

  /** 当前列表中命中形态的股票代码集合：key=patternKey, value=Set<code> */
  const patternHits = useMemo(() => {
    const hits = {} as Record<PatternKey, Set<string>>
    PATTERN_KEYS.forEach(k => { hits[k] = new Set() })
    Object.entries(patternResults).forEach(([code, patterns]) => {
      patterns.forEach(p => hits[p].add(code))
    })
    return hits
  }, [patternResults])

  // ========== 事件处理：显示/隐藏 K线图 ==========
  const handleShowKLine = useCallback((stockCode: string) => {
    setShowKLine(true)
    fetchKLineData(stockCode)
  }, [fetchKLineData])

  const handleCloseKLine = useCallback(() => {
    setShowKLine(false)
    clearKLineData()
  }, [clearKLineData])

  // ========== 筛选状态 ==========
  /** 激活的筛选条件数组（如：break_high_20, pattern_hammer 等） */
  const [activeFilters, setActiveFilters] = useState<string[]>([])
  /** 激活的行业数组 */
  const [activeIndustries, setActiveIndustries] = useState<string[]>([])
  /** 激活的地区数组 */
  const [activeAreas, setActiveAreas] = useState<string[]>([])

  /**
   * 形态字段过滤后的股票列表
   * - 如果 activeFilters 中没有形态字段，返回原列表
   * - 如果有，要求股票命中所有激活的形态（AND 关系）
   */
  const filteredStocks = useMemo(() => {
    if (!stocks) return null
    const activePatterns = activeFilters.filter(k => PATTERN_KEYS.includes(k as PatternKey)) as PatternKey[]
    if (activePatterns.length === 0) return stocks
    return stocks.filter(s =>
      activePatterns.every(p => patternHits[p]?.has(s.stock_code))
    )
  }, [stocks, activeFilters, patternHits])

  // ========== 排序状态 ==========
  /** 当前排序字段（默认按涨跌幅排序） */
  const [sortBy, setSortBy] = useState('change_pct')
  /** 是否升序排列（默认降序） */
  const [sortAsc, setSortAsc] = useState(false)

  // ========== 分页状态 ==========
  /** 当前页偏移量 */
  const [offset, setOffset] = useState(0)

  // ========== 副作用：加载元数据 ==========
  /**
   * 组件挂载时加载元数据
   * 仅执行一次（空依赖数组）
   */
  useEffect(() => {
    fetchMeta()
      .then((res: ApiResponse<MetaResponseData>) => {
        if (res.code === 200 && res.data) {
          setMeta(filterMetaGroups(res.data))
        } else {
          setError(res.message || '获取元数据失败')
        }
      })
      .catch(e => setError(e.message))
  }, [])

  // ========== 副作用：加载股票列表 ==========
  /**
   * 当筛选条件、排序、分页变化时重新加载股票列表
   * 使用 AbortController 取消过期的请求，避免竞态条件
   * 
   * 依赖项：
   * - meta: 元数据加载完成后才开始加载股票
   * - activeFilters, activeIndustries, activeAreas: 筛选条件
   * - sortBy, sortAsc: 排序条件
   * - offset: 分页偏移
   */
  useEffect(() => {
    // 元数据未加载时不执行
    if (!meta) return
    
    // 创建 AbortController 用于取消请求
    const controller = new AbortController()
    
    // 设置加载状态
    setLoading(true)
    setError(null)
    
    // 构造 as_of_date（使用元数据中的交易日期）
    const as_of_date = meta.trade_date
    
    // 调用 API 获取股票列表
    fetchStocks({ 
      industry: activeIndustries.length > 0 ? activeIndustries.join(',') : undefined,
      area: activeAreas.length > 0 ? activeAreas.join(',') : undefined,
      // 形态字段不在后端过滤（数据缺失），改为前端二次过滤
      filters: activeFilters.filter(k => !PATTERN_KEYS.includes(k as PatternKey)).join(',') || undefined,
      sort_by: sortBy,
      sort_asc: sortAsc,
      offset,
      limit: LIMIT,
      as_of_date
    }, { signal: controller.signal })
      .then((res: ApiResponse<StockListResponse>) => {
        if (res.code === 200 && res.data) {
          setStocks(res.data.items)
          setTotal(res.data.total)
          // 触发前端形态识别（先查 localStorage 缓存，未命中才拉 K线）
          const codes = res.data.items.map(s => s.stock_code)
          if (codes.length > 0) {
            fetchBatchKLine(codes, as_of_date, 5)
          }
        } else {
          setError(res.message || '获取股票列表失败')
        }
      })
      .catch(e => { 
        // 忽略主动中止的错误
        if (e.name !== 'AbortError') setError(e.message) 
      })
      .finally(() => setLoading(false))
    
    // 清理函数：组件卸载或依赖变化时中止请求
    return () => controller.abort()
  }, [meta, activeFilters, activeIndustries, activeAreas, sortBy, sortAsc, offset])

  // ========== 事件处理函数 ==========
  
  /**
   * 切换筛选条件
   * @param key - 筛选条件键名
   * 
   * 逻辑：
   * - 如果已激活，则移除
   * - 如果未激活，则添加
   * - 重置分页到第一页
   */
  const toggleFilter = useCallback((key: string) => {
    setOffset(0) // 重置分页
    setActiveFilters(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    )
  }, [])

  /**
   * 切换行业筛选
   * @param val - 行业名称
   */
  const toggleIndustry = useCallback((val: string) => {
    setOffset(0) // 重置分页
    setActiveIndustries(prev =>
      prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val]
    )
  }, [])

  /**
   * 切换地区筛选
   * @param val - 地区名称
   */
  const toggleArea = useCallback((val: string) => {
    setOffset(0) // 重置分页
    setActiveAreas(prev =>
      prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val]
    )
  }, [])

  /**
   * 清空所有筛选条件
   */
  const clearAll = useCallback(() => {
    setOffset(0) // 重置分页
    setActiveFilters([])
    setActiveIndustries([])
    setActiveAreas([])
  }, [])

  /**
   * 从状态栏删除单个筛选条件
   * 支持特殊前缀：__industry__ 和 __area__
   * 
   * @param key - 筛选条件键名（可能包含前缀）
   */
  const removeFilter = useCallback((key: string) => {
    // 处理行业筛选
    if (key.startsWith('__industry__')) {
      toggleIndustry(key.replace('__industry__', ''))
    } 
    // 处理地区筛选
    else if (key.startsWith('__area__')) {
      toggleArea(key.replace('__area__', ''))
    } 
    // 处理普通筛选
    else {
      toggleFilter(key)
    }
  }, [toggleFilter, toggleIndustry, toggleArea])

  /**
   * 处理排序
   * @param key - 排序字段
   * 
   * 逻辑：
   * - 如果是同一字段，切换升降序
   * - 如果是不同字段，设置为降序
   * - 重置分页到第一页
   */
  const handleSort = useCallback((key: string) => {
    setOffset(0) // 重置分页
    if (sortBy === key) {
      // 同一字段：切换升降序
      setSortAsc(a => !a)
    } else {
      // 不同字段：设置为新字段，默认降序
      setSortBy(key)
      setSortAsc(false)
    }
  }, [sortBy])

  // ========== 构建筛选标签映射 ==========
  /**
   * 从元数据中构建筛选条件标签映射
   * 用于状态栏显示友好的标签名称
   */
  const filterLabels: Record<string, string> = {}
  if (meta?.groups) {
    (meta.groups as FilterGroup[]).forEach(g => {
      g.fields.forEach(f => { 
        filterLabels[f.key] = f.label 
      })
    })
  }

  // ========== 错误状态渲染 ==========
  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-900 text-red-400">
        错误：{error}
      </div>
    )
  }

  // ========== 加载状态渲染 ==========
  if (!meta) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-900 text-gray-400">
        加载中…
      </div>
    )
  }

  // ========== 正常状态渲染 ==========
  return (
    <div className="flex flex-col h-screen bg-gray-900 text-gray-200">
      {/* 顶部状态栏 */}
      <StatusBar
        tradeDate={meta.trade_date}
        matchCount={total}
        totalCount={meta.total}
        activeFilters={activeFilters}
        activeIndustries={activeIndustries}
        activeAreas={activeAreas}
        filterLabels={filterLabels}
        onClearAll={clearAll}
        onRemoveFilter={removeFilter}
      />

      {/* 主体区域 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧筛选面板 */}
        <FilterPanel
          groups={meta.groups as FilterGroup[]}
          industryOptions={meta.industry_options}
          areaOptions={meta.area_options}
          activeFilters={activeFilters}
          activeIndustries={activeIndustries}
          activeAreas={activeAreas}
          onToggleFilter={toggleFilter}
          onToggleIndustry={toggleIndustry}
          onToggleArea={toggleArea}
        />

        {/* 右侧主内容区 */}
        <main className="flex flex-col flex-1 overflow-hidden relative">
          {/* 加载提示 */}
          {loading && (
            <div className="absolute top-2 right-4 text-xs text-gray-500 animate-pulse z-20">
              查询中…
            </div>
          )}
          {/* 形态识别进行中提示 */}
          {batchKLineLoading && !loading && (
            <div className="absolute top-2 right-4 text-xs text-yellow-500 animate-pulse z-20">
              形态识别中 {batchKLineProgress.current}/{batchKLineProgress.total}
              {patternCacheHits + klineCacheHits > 0 &&
                ` (缓存 ${patternCacheHits}+${klineCacheHits})`}…
            </div>
          )}
          
          {/* 股票表格或 K线图表 */}
          {showKLine ? (
            <div className="flex flex-col h-full p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-white">K线分析</h2>
                <button
                  onClick={handleCloseKLine}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white transition-colors"
                >
                  返回列表
                </button>
              </div>
              <div className="bg-white rounded-lg p-4 flex-1 overflow-hidden">
                <KLineChart
                  data={klineData}
                  loading={klineLoading}
                  error={klineError}
                  stockCode={klineStockCode}
                  height={500}
                />
              </div>
            </div>
          ) : (
            filteredStocks && (
              <StockTable
                rows={filteredStocks}
                total={total}
                offset={offset}
                limit={LIMIT}
                sortBy={sortBy}
                sortAsc={sortAsc}
                activeFilters={activeFilters}
                onSort={handleSort}
                onPageChange={setOffset}
                onRowClick={handleShowKLine}
              />
            )
          )}
        </main>
      </div>
    </div>
  )
}
