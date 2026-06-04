interface Props {
  tradeDate: string
  matchCount: number
  totalCount: number
  activeFilters: string[]
  activeIndustries: string[]
  activeAreas: string[]
  filterLabels: Record<string, string>
  onClearAll: () => void
  onRemoveFilter: (key: string) => void
}

function formatDate(raw: string): string {
  if (raw.length !== 8) return raw
  return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
}

export default function StatusBar({
  tradeDate, matchCount, totalCount,
  activeFilters, activeIndustries, activeAreas,
  filterLabels, onClearAll, onRemoveFilter,
}: Props) {
  const hasAny = activeFilters.length > 0 || activeIndustries.length > 0 || activeAreas.length > 0

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2 bg-gray-900 border-b border-gray-700 text-sm">
      <span className="text-gray-400 shrink-0">
        交易日：<span className="text-white font-mono">{formatDate(tradeDate)}</span>
      </span>

      <span className="text-gray-600">|</span>

      <span className="text-gray-400 shrink-0">
        匹配：
        <span className="text-red-400 font-bold">{matchCount.toLocaleString()}</span>
        <span className="text-gray-500"> / {totalCount.toLocaleString()} 只</span>
      </span>

      {hasAny && (
        <>
          <span className="text-gray-600">|</span>
          <div className="flex flex-wrap gap-1">
            {activeFilters.map(key => (
              <div
                key={key}
                className="flex items-center gap-1 bg-red-900/50 text-red-300 text-xs px-2 py-0.5 rounded-full"
              >
                {filterLabels[key] ?? key}
                <button
                  onClick={() => onRemoveFilter(key)}
                  aria-label="删除"
                  className="hover:text-white leading-none"
                >×</button>
              </div>
            ))}
            {activeIndustries.map(ind => (
              <div key={ind} className="flex items-center gap-1 bg-blue-900/50 text-blue-300 text-xs px-2 py-0.5 rounded-full">
                {ind}
                <button onClick={() => onRemoveFilter(`__industry__${ind}`)} aria-label="删除" className="hover:text-white leading-none">×</button>
              </div>
            ))}
            {activeAreas.map(area => (
              <div key={area} className="flex items-center gap-1 bg-purple-900/50 text-purple-300 text-xs px-2 py-0.5 rounded-full">
                {area}
                <button onClick={() => onRemoveFilter(`__area__${area}`)} aria-label="删除" className="hover:text-white leading-none">×</button>
              </div>
            ))}
          </div>
          <button
            onClick={onClearAll}
            className="ml-auto text-xs text-gray-400 hover:text-white border border-gray-600 hover:border-gray-400 px-2 py-0.5 rounded"
          >
            清空条件
          </button>
        </>
      )}
    </div>
  )
}