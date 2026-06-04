import { useState } from 'react'
import type { FilterGroup } from '../types'

interface Props {
  groups: FilterGroup[]
  industryOptions: string[]
  areaOptions: string[]
  activeFilters: string[]
  activeIndustries: string[]
  activeAreas: string[]
  onToggleFilter: (key: string) => void
  onToggleIndustry: (value: string) => void
  onToggleArea: (value: string) => void
}

function GroupSection({
  group, activeFilters, onToggleFilter, initialOpen = false,
}: {
  group: FilterGroup
  activeFilters: string[]
  onToggleFilter: (key: string) => void
  initialOpen?: boolean
}) {
  const [open, setOpen] = useState(initialOpen)
  const activeCount = group.fields.filter(f => activeFilters.includes(f.key)).length

  return (
    <div className="border-b border-gray-700">
      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-700"
      >
        <span>
          {group.label}
          {activeCount > 0 && (
            <span className="ml-2 bg-red-700 text-white text-xs px-1.5 rounded-full">
              {activeCount}
            </span>
          )}
        </span>
        <span className="text-gray-500 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-2 pb-2 flex flex-wrap gap-1.5">
          {group.fields.map(field => {
            const active = activeFilters.includes(field.key)
            // count 为 0 时也允许点击（后端可能没及时更新统计），不显示误导性的"0"
            const showCount = field.count > 0
            return (
              <button
                key={field.key}
                onClick={() => onToggleFilter(field.key)}
                title={showCount ? `命中 ${field.count} 只` : '点击筛选'}
                className={[
                  'text-xs px-2 py-0.5 rounded-full border transition-colors',
                  active
                    ? 'bg-red-700 border-red-600 text-white'
                    : showCount
                      ? 'bg-gray-800 border-gray-600 text-gray-300 hover:border-red-500 hover:text-red-300'
                      : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-red-500 hover:text-red-300',
                ].join(' ')}
              >
                {field.label}
                {showCount && (
                  <span className="ml-1 opacity-60">{field.count}</span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function MultiSelectSection({
  label, options, active, onToggle,
}: {
  label: string
  options: string[]
  active: string[]
  onToggle: (v: string) => void
}) {
  const [open, setOpen] = useState(true)

  return (
    <div className="border-b border-gray-700">
      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-700"
      >
        <span>
          {label}
          {active.length > 0 && (
            <span className="ml-2 bg-blue-700 text-white text-xs px-1.5 rounded-full">
              {active.length}
            </span>
          )}
        </span>
        <span className="text-gray-500 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-2 pb-2 flex flex-wrap gap-1.5">
          {options.map(opt => (
            <button
              key={opt}
              onClick={() => onToggle(opt)}
              className={[
                'text-xs px-2 py-0.5 rounded-full border transition-colors',
                active.includes(opt)
                  ? 'bg-blue-700 border-blue-600 text-white'
                  : 'bg-gray-800 border-gray-600 text-gray-300 hover:border-blue-500',
              ].join(' ')}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function FilterPanel({
  groups, industryOptions, areaOptions,
  activeFilters, activeIndustries, activeAreas,
  onToggleFilter, onToggleIndustry, onToggleArea,
}: Props) {
  return (
    <aside className="w-56 shrink-0 bg-gray-800 border-r border-gray-700 overflow-y-auto">
      <div className="px-3 py-2 text-xs font-bold text-gray-400 uppercase tracking-wider border-b border-gray-700">
        筛选条件
      </div>

      {groups.map((group) => (
        <GroupSection
          key={group.id}
          group={group}
          activeFilters={activeFilters}
          onToggleFilter={onToggleFilter}
          initialOpen={group.id === 'momentum'}
        />
      ))}

      <MultiSelectSection
        label="行业"
        options={industryOptions}
        active={activeIndustries}
        onToggle={onToggleIndustry}
      />
      <MultiSelectSection
        label="地区"
        options={areaOptions}
        active={activeAreas}
        onToggle={onToggleArea}
      />
    </aside>
  )
}