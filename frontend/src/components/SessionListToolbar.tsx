'use client'

export type SessionFilterKey = 'all' | 'active' | 'running' | 'pending' | 'completed' | 'failed'
export type SessionSortKey = 'newest' | 'oldest' | 'status'

export interface SessionListCounts {
  all: number
  active: number
  running?: number
  pending?: number
  completed: number
  failed: number
}

interface Props {
  filter: SessionFilterKey
  sort: SessionSortKey
  counts: SessionListCounts
  onFilterChange: (f: SessionFilterKey) => void
  onSortChange: (s: SessionSortKey) => void
  /** Show running/pending sub-tabs. Default true. */
  showSubTabs?: boolean
}

const FILTER_TABS: { key: SessionFilterKey; label: string }[] = [
  { key: 'all',       label: 'All'       },
  { key: 'active',    label: 'Active'    },
  { key: 'completed', label: 'Done'      },
  { key: 'failed',    label: 'Failed'    },
]

const SUB_TABS: { key: SessionFilterKey; label: string }[] = [
  { key: 'running', label: 'Running' },
  { key: 'pending', label: 'Pending' },
]

export default function SessionListToolbar({
  filter,
  sort,
  counts,
  onFilterChange,
  onSortChange,
  showSubTabs = true,
}: Props) {
  const tabs = showSubTabs
    ? [...FILTER_TABS.slice(0, 2), ...SUB_TABS, ...FILTER_TABS.slice(2)]
    : FILTER_TABS

  return (
    <div className="flex items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-700">
      {/* Filter tabs */}
      <div className="flex items-center gap-0.5 overflow-x-auto">
        {tabs.map(({ key, label }) => {
          const count = counts[key as keyof SessionListCounts] ?? 0
          const active = filter === key
          return (
            <button
              key={key}
              onClick={() => onFilterChange(key)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                active
                  ? 'border-orange-500 text-orange-600 dark:text-orange-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              {label}
              {count > 0 && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                  active
                    ? 'bg-orange-100 text-orange-600 dark:bg-orange-900/30'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-500'
                }`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Sort control */}
      <div className="flex-shrink-0 pb-1">
        <select
          value={sort}
          onChange={e => onSortChange(e.target.value as SessionSortKey)}
          className="text-xs border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 focus:outline-none focus:border-orange-400"
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="status">By status</option>
        </select>
      </div>
    </div>
  )
}
