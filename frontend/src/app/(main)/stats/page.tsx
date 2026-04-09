'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

interface CostSummary {
  total_cost: number
  by_model: Record<string, number>
  by_provider: Record<string, number>
}

interface UsageSummary {
  total_requests: number
  total_input_tokens: number
  total_output_tokens: number
  success_rate: number
  by_model: Record<string, { requests: number; input_tokens: number; output_tokens: number }>
}

// --- New interfaces for daily cost trend ---

interface DailyCostEntry {
  date: string
  total_cost: number
  total_requests: number
  input_tokens: number
  output_tokens: number
}

interface DailyCostSummary {
  total_cost: number
  daily_average: number
  change_pct: number | null
}

interface DailyCostResponse {
  daily: DailyCostEntry[]
  summary: DailyCostSummary
}

interface FeedbackModelEntry {
  model_id: string | null
  total: number
  positive: number
  negative: number
  satisfaction_rate: number
}

interface FeedbackSummary {
  by_model: FeedbackModelEntry[]
  period_days: number
}

// --- Helpers ---
interface ModelPerformanceMetrics {
  model_name: string
  display_name: string | null
  total_requests: number
  avg_latency_ms: number
  p95_latency_ms: number
  success_rate: number
  avg_tokens_per_request: number
  total_cost: number
}

interface ModelPerformanceHighlights {
  cheapest: string | null
  fastest: string | null
  most_reliable: string | null
}

interface ModelPerformanceSummary {
  models: ModelPerformanceMetrics[]
  highlights: ModelPerformanceHighlights
}

type SortKey = keyof Pick<
  ModelPerformanceMetrics,
  'model_name' | 'total_requests' | 'avg_latency_ms' | 'p95_latency_ms' | 'success_rate' | 'avg_tokens_per_request' | 'total_cost'
>

function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

function formatCost(cost: number): string {
  if (cost === 0) return '$0.00'
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// --- SVG Line Chart Component ---

interface ChartTooltip {
  x: number
  y: number
  date: string
  cost: number
}

function CostLineChart({ data }: { data: DailyCostEntry[] }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [tooltip, setTooltip] = useState<ChartTooltip | null>(null)
  const [dimensions, setDimensions] = useState({ width: 700, height: 300 })

  const updateDimensions = useCallback(() => {
    if (svgRef.current?.parentElement) {
      const parentWidth = svgRef.current.parentElement.clientWidth
      setDimensions({ width: Math.max(parentWidth - 32, 300), height: 300 })
    }
  }, [])

  useEffect(() => {
    updateDimensions()
    window.addEventListener('resize', updateDimensions)
    return () => window.removeEventListener('resize', updateDimensions)
  }, [updateDimensions])

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
        No daily cost data available
      </div>
    )
  }

  const padding = { top: 20, right: 20, bottom: 40, left: 60 }
  const chartWidth = dimensions.width - padding.left - padding.right
  const chartHeight = dimensions.height - padding.top - padding.bottom

  const costs = data.map(d => d.total_cost)
  const maxCost = Math.max(...costs, 0.01) // minimum scale so chart renders
  const minCost = 0

  // Compute scales
  const xScale = (i: number) => padding.left + (i / Math.max(data.length - 1, 1)) * chartWidth
  const yScale = (v: number) => padding.top + chartHeight - ((v - minCost) / (maxCost - minCost)) * chartHeight

  // Build polyline path
  const points = data.map((d, i) => `${xScale(i)},${yScale(d.total_cost)}`).join(' ')

  // Build area path (filled under the line)
  const areaPath = [
    `M ${xScale(0)},${yScale(data[0].total_cost)}`,
    ...data.slice(1).map((d, i) => `L ${xScale(i + 1)},${yScale(d.total_cost)}`),
    `L ${xScale(data.length - 1)},${padding.top + chartHeight}`,
    `L ${xScale(0)},${padding.top + chartHeight}`,
    'Z'
  ].join(' ')

  // Y-axis ticks (5 ticks)
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const val = minCost + ((maxCost - minCost) * i) / 4
    return { val, y: yScale(val) }
  })

  // X-axis labels -- show ~6-8 labels max
  const labelInterval = Math.max(1, Math.ceil(data.length / 7))
  const xLabels = data
    .map((d, i) => ({ label: formatDate(d.date), x: xScale(i), i }))
    .filter((_, i) => i % labelInterval === 0 || i === data.length - 1)

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current || data.length === 0) return
    const rect = svgRef.current.getBoundingClientRect()
    const mouseX = e.clientX - rect.left

    // Find nearest data point
    let nearestIdx = 0
    let nearestDist = Infinity
    for (let i = 0; i < data.length; i++) {
      const dist = Math.abs(xScale(i) - mouseX)
      if (dist < nearestDist) {
        nearestDist = dist
        nearestIdx = i
      }
    }

    if (nearestDist < 40) {
      setTooltip({
        x: xScale(nearestIdx),
        y: yScale(data[nearestIdx].total_cost),
        date: data[nearestIdx].date,
        cost: data[nearestIdx].total_cost,
      })
    } else {
      setTooltip(null)
    }
  }

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        className="overflow-visible"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTooltip(null)}
      >
        {/* Grid lines */}
        {yTicks.map((tick, i) => (
          <line
            key={i}
            x1={padding.left}
            y1={tick.y}
            x2={padding.left + chartWidth}
            y2={tick.y}
            stroke="#e5e7eb"
            strokeWidth={1}
          />
        ))}

        {/* Y-axis labels */}
        {yTicks.map((tick, i) => (
          <text
            key={i}
            x={padding.left - 8}
            y={tick.y + 4}
            textAnchor="end"
            className="fill-gray-500"
            fontSize={11}
          >
            {formatCost(tick.val)}
          </text>
        ))}

        {/* X-axis labels */}
        {xLabels.map((lbl, i) => (
          <text
            key={i}
            x={lbl.x}
            y={padding.top + chartHeight + 24}
            textAnchor="middle"
            className="fill-gray-500"
            fontSize={11}
          >
            {lbl.label}
          </text>
        ))}

        {/* Area fill */}
        <path d={areaPath} fill="url(#costGradient)" opacity={0.3} />

        {/* Gradient definition */}
        <defs>
          <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>

        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke="#3b82f6"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Data points */}
        {data.map((d, i) => (
          <circle
            key={i}
            cx={xScale(i)}
            cy={yScale(d.total_cost)}
            r={3}
            fill="#3b82f6"
            stroke="white"
            strokeWidth={1.5}
          />
        ))}

        {/* Tooltip crosshair and dot */}
        {tooltip && (
          <>
            <line
              x1={tooltip.x}
              y1={padding.top}
              x2={tooltip.x}
              y2={padding.top + chartHeight}
              stroke="#9ca3af"
              strokeDasharray="4 2"
              strokeWidth={1}
            />
            <circle
              cx={tooltip.x}
              cy={tooltip.y}
              r={5}
              fill="#2563eb"
              stroke="white"
              strokeWidth={2}
            />
          </>
        )}
      </svg>

      {/* Tooltip box */}
      {tooltip && (
        <div
          className="absolute bg-gray-900 text-white text-xs rounded px-3 py-2 pointer-events-none shadow-lg"
          style={{
            left: tooltip.x,
            top: tooltip.y - 48,
            transform: 'translateX(-50%)',
          }}
        >
          <div className="font-medium">{formatDate(tooltip.date)}</div>
          <div className="text-blue-300">{formatCost(tooltip.cost)}</div>
        </div>
      )}
    </div>
  )
}

// --- Change Indicator ---

function ChangeIndicator({ changePct }: { changePct: number | null }) {
  if (changePct === null) {
    return <span className="text-sm text-gray-400">N/A (no prior data)</span>
  }
  const isPositive = changePct > 0
  const isZero = changePct === 0
  const color = isZero ? 'text-gray-500' : isPositive ? 'text-red-600' : 'text-green-600'
  const arrow = isZero ? '' : isPositive ? '\u2191' : '\u2193'

  return (
    <span className={`text-sm font-medium ${color}`}>
      {arrow} {Math.abs(changePct).toFixed(1)}%
    </span>
  )
}

function formatLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}

/* ------------------------------------------------------------------ */
/*  Model Performance Table (sortable) + Latency Bar Chart            */
/* ------------------------------------------------------------------ */

function ModelPerformanceSection({ performance }: { performance: ModelPerformanceSummary }) {
  const [sortKey, setSortKey] = useState<SortKey>('total_requests')
  const [sortAsc, setSortAsc] = useState(false)

  const handleSort = useCallback((key: SortKey) => {
    if (key === sortKey) {
      setSortAsc(prev => !prev)
    } else {
      setSortKey(key)
      // Default descending for numbers, ascending for names
      setSortAsc(key === 'model_name')
    }
  }, [sortKey])

  const sorted = useMemo(() => {
    const list = [...performance.models]
    list.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      const diff = (av as number) - (bv as number)
      return sortAsc ? diff : -diff
    })
    return list
  }, [performance.models, sortKey, sortAsc])

  const { highlights } = performance

  // Badge helper — returns a label if the model matches a highlight
  function badge(m: ModelPerformanceMetrics): { label: string; color: string } | null {
    const name = m.display_name || m.model_name
    if (name === highlights.fastest) return { label: 'Fastest', color: 'bg-blue-100 text-blue-800' }
    if (name === highlights.cheapest) return { label: 'Cheapest', color: 'bg-green-100 text-green-800' }
    if (name === highlights.most_reliable) return { label: 'Most Reliable', color: 'bg-purple-100 text-purple-800' }
    return null
  }

  // Column header with sort indicator
  function SortHeader({ label, field, align }: { label: string; field: SortKey; align?: string }) {
    const active = sortKey === field
    return (
      <th
        onClick={() => handleSort(field)}
        className={`px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700 ${align === 'right' ? 'text-right' : 'text-left'}`}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active && <span className="text-gray-800">{sortAsc ? '\u25B2' : '\u25BC'}</span>}
        </span>
      </th>
    )
  }

  // Bar chart: max latency determines 100% width
  const maxLatency = useMemo(
    () => Math.max(...performance.models.map(m => m.avg_latency_ms), 1),
    [performance.models]
  )

  if (performance.models.length === 0) {
    return (
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Model Performance Comparison</h2>
        <div className="bg-white shadow sm:rounded-lg px-6 py-4 text-sm text-gray-500 text-center">
          No performance data available yet
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Highlights bar */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Model Performance Comparison</h2>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          {highlights.fastest && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
              <span className="text-xl">&#9889;</span>
              <div>
                <p className="text-xs font-medium text-blue-600 uppercase">Fastest</p>
                <p className="text-sm font-semibold text-blue-900">{highlights.fastest}</p>
              </div>
            </div>
          )}
          {highlights.cheapest && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
              <span className="text-xl">&#128176;</span>
              <div>
                <p className="text-xs font-medium text-green-600 uppercase">Cheapest</p>
                <p className="text-sm font-semibold text-green-900">{highlights.cheapest}</p>
              </div>
            </div>
          )}
          {highlights.most_reliable && (
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 flex items-center gap-3">
              <span className="text-xl">&#9989;</span>
              <div>
                <p className="text-xs font-medium text-purple-600 uppercase">Most Reliable</p>
                <p className="text-sm font-semibold text-purple-900">{highlights.most_reliable}</p>
              </div>
            </div>
          )}
        </div>

        {/* Sortable table */}
        <div className="bg-white shadow overflow-x-auto sm:rounded-lg">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <SortHeader label="Model" field="model_name" />
                <SortHeader label="Requests" field="total_requests" align="right" />
                <SortHeader label="Avg Latency" field="avg_latency_ms" align="right" />
                <SortHeader label="P95 Latency" field="p95_latency_ms" align="right" />
                <SortHeader label="Success Rate" field="success_rate" align="right" />
                <SortHeader label="Avg Tokens" field="avg_tokens_per_request" align="right" />
                <SortHeader label="Cost" field="total_cost" align="right" />
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {sorted.map((m) => {
                const b = badge(m)
                return (
                  <tr key={m.model_name} className="hover:bg-gray-50">
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      <span className="flex items-center gap-2">
                        {m.display_name || m.model_name}
                        {b && (
                          <span className={`inline-flex text-[10px] font-semibold px-1.5 py-0.5 rounded ${b.color}`}>
                            {b.label}
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatNumber(m.total_requests)}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatLatency(m.avg_latency_ms)}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatLatency(m.p95_latency_ms)}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-right">
                      <span className={m.success_rate >= 99 ? 'text-green-600 font-medium' : m.success_rate >= 90 ? 'text-yellow-600' : 'text-red-600 font-medium'}>
                        {m.success_rate.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatNumber(m.avg_tokens_per_request)}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                      {formatCost(m.total_cost)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Latency Bar Chart */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Latency Comparison</h2>
        <div className="bg-white shadow sm:rounded-lg p-6 space-y-3">
          {performance.models
            .sort((a, b) => a.avg_latency_ms - b.avg_latency_ms)
            .map((m) => {
              const pct = (m.avg_latency_ms / maxLatency) * 100
              const name = m.display_name || m.model_name
              const isFastest = name === highlights.fastest
              return (
                <div key={m.model_name} className="flex items-center gap-3">
                  <div className="w-40 text-sm text-gray-700 truncate text-right" title={name}>
                    {name}
                  </div>
                  <div className="flex-1 h-6 bg-gray-100 rounded overflow-hidden relative">
                    <div
                      className={`h-full rounded ${isFastest ? 'bg-blue-500' : 'bg-indigo-400'}`}
                      style={{ width: `${Math.max(pct, 2)}%` }}
                    />
                  </div>
                  <div className="w-20 text-sm text-gray-600 tabular-nums text-right">
                    {formatLatency(m.avg_latency_ms)}
                  </div>
                </div>
              )
            })}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

const TIME_RANGE_OPTIONS = [7, 14, 30] as const

export default function StatsPage() {
  const [costs, setCosts] = useState<CostSummary | null>(null)
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [dailyCosts, setDailyCosts] = useState<DailyCostResponse | null>(null)
  const [feedback, setFeedback] = useState<FeedbackSummary | null>(null)
  const [performance, setPerformance] = useState<ModelPerformanceSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedDays, setSelectedDays] = useState<number>(7)
  const [perfDays, setPerfDays] = useState(7)

  // Fetch core stats once
  useEffect(() => {
    async function fetchStats() {
      try {
        const [costsRes, usageRes, feedbackRes] = await Promise.all([
          fetch(`${API_BASE}/v1/stats/costs?days=7`, {
            headers: { ...AUTH_HEADERS }
          }).then(r => r.json()),
          fetch(`${API_BASE}/v1/stats/usage?days=7`, {
            headers: { ...AUTH_HEADERS }
          }).then(r => r.json()),
          fetch(`${API_BASE}/v1/feedback?days=7`, {
            headers: { ...AUTH_HEADERS }
          }).then(r => r.json()).catch(() => null)
        ])
        setCosts(costsRes)
        setUsage(usageRes)
        if (feedbackRes) setFeedback(feedbackRes)
      } catch (e) {
        console.error('Failed to fetch stats:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchStats()
  }, [])

  // Fetch daily cost trend (when selectedDays changes)
  useEffect(() => {
    async function fetchDailyCosts() {
      try {
        const res = await fetch(`${API_BASE}/v1/stats/costs/daily?days=${selectedDays}`, {
          headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
        })
        const data: DailyCostResponse = await res.json()
        setDailyCosts(data)
      } catch (e) {
        console.error('Failed to fetch daily costs:', e)
      }
    }
    fetchDailyCosts()
  }, [selectedDays])
  // Fetch performance data (reactive to day selector)
  useEffect(() => {
    async function fetchPerformance() {
      try {
        const res = await fetch(`${API_BASE}/v1/stats/models/performance?days=${perfDays}`, {
          headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
        })
        if (res.ok) {
          const data = await res.json()
          setPerformance(data)
        }
      } catch (e) {
        console.error('Failed to fetch model performance:', e)
      }
    }
    fetchPerformance()
  }, [perfDays])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (!costs || !usage) {
    return (
      <div className="text-center py-12">
        <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <h3 className="mt-2 text-sm font-medium text-gray-900">No stats available</h3>
        <p className="mt-1 text-sm text-gray-500">
          Start making requests through the API to see statistics.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Statistics</h1>
        <p className="mt-1 text-sm text-gray-500">
          Usage and cost analytics for the last 7 days
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Total Cost
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {formatCost(costs.total_cost)}
            </dd>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Total Requests
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {formatNumber(usage.total_requests)}
            </dd>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Input Tokens
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {formatNumber(usage.total_input_tokens)}
            </dd>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Output Tokens
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {formatNumber(usage.total_output_tokens)}
            </dd>
          </div>
        </div>
      </div>

      {/* Cost Trend Chart */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-900">Cost Trend</h2>
          <div className="flex rounded-md shadow-sm">
            {TIME_RANGE_OPTIONS.map((days) => (
              <button
                key={days}
                onClick={() => setSelectedDays(days)}
                className={`px-3 py-1.5 text-sm font-medium border ${
                  selectedDays === days
                    ? 'bg-blue-600 text-white border-blue-600 z-10'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                } ${
                  days === 7 ? 'rounded-l-md' : ''
                } ${
                  days === 30 ? 'rounded-r-md' : ''
                } ${
                  days !== 7 ? '-ml-px' : ''
                }`}
              >
                {days}d
              </button>
            ))}
          </div>
        </div>

        <div className="bg-white shadow rounded-lg p-4">
          {dailyCosts ? (
            <CostLineChart data={dailyCosts.daily} />
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
              Loading chart...
            </div>
          )}
        </div>

        {/* Trend Summary Cards */}
        {dailyCosts && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 mt-4">
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="px-4 py-5 sm:p-6">
                <dt className="text-sm font-medium text-gray-500 truncate">
                  Period Total
                </dt>
                <dd className="mt-1 text-2xl font-semibold text-gray-900">
                  {formatCost(dailyCosts.summary.total_cost)}
                </dd>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="px-4 py-5 sm:p-6">
                <dt className="text-sm font-medium text-gray-500 truncate">
                  Daily Average
                </dt>
                <dd className="mt-1 text-2xl font-semibold text-gray-900">
                  {formatCost(dailyCosts.summary.daily_average)}
                </dd>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="px-4 py-5 sm:p-6">
                <dt className="text-sm font-medium text-gray-500 truncate">
                  vs Prior Period
                </dt>
                <dd className="mt-1 text-2xl font-semibold text-gray-900">
                  <ChangeIndicator changePct={dailyCosts.summary.change_pct} />
                </dd>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Cost by Model */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Cost by Model</h2>
        <div className="bg-white shadow overflow-hidden sm:rounded-lg">
          {Object.keys(costs.by_model).length > 0 ? (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    % of Total
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {Object.entries(costs.by_model).map(([model, cost]) => (
                  <tr key={model}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {model}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatCost(cost)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {costs.total_cost > 0 ? `${((cost / costs.total_cost) * 100).toFixed(1)}%` : '0%'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="px-6 py-4 text-sm text-gray-500 text-center">
              No cost data available yet
            </div>
          )}
        </div>
      </div>

      {/* Usage by Model */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Usage by Model</h2>
        <div className="bg-white shadow overflow-hidden sm:rounded-lg">
          {Object.keys(usage.by_model).length > 0 ? (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Requests
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Input Tokens
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Output Tokens
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {Object.entries(usage.by_model).map(([model, data]) => (
                  <tr key={model}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {model}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatNumber(data.requests)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatNumber(data.input_tokens)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatNumber(data.output_tokens)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="px-6 py-4 text-sm text-gray-500 text-center">
              No usage data available yet
            </div>
          )}
        </div>
      </div>

      {/* Success Rate */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Success Rate</h2>
        <div className="bg-white shadow sm:rounded-lg p-6">
          <div className="flex items-center">
            <div className="flex-1">
              <div className="h-4 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full"
                  style={{ width: `${usage.success_rate * 100}%` }}
                />
              </div>
            </div>
            <div className="ml-4">
              <span className="text-2xl font-semibold text-gray-900">
                {(usage.success_rate * 100).toFixed(1)}%
              </span>
            </div>
          </div>
          <p className="mt-2 text-sm text-gray-500">
            {usage.total_requests} total requests in the last 7 days
          </p>
        </div>
      </div>

      {/* User Satisfaction (Feedback) */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">User Satisfaction</h2>
        <div className="bg-white shadow overflow-hidden sm:rounded-lg">
          {feedback && feedback.by_model && feedback.by_model.length > 0 ? (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Positive
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Negative
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Total
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Satisfaction
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {feedback.by_model.map((entry) => (
                  <tr key={entry.model_id || 'unknown'}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {entry.model_id || 'Unknown'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-green-600">
                      {entry.positive}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-red-600">
                      {entry.negative}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {entry.total}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden max-w-[100px]">
                          <div
                            className={`h-full rounded-full ${
                              entry.satisfaction_rate >= 70 ? 'bg-green-500' :
                              entry.satisfaction_rate >= 40 ? 'bg-yellow-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${entry.satisfaction_rate}%` }}
                          />
                        </div>
                        <span className="text-gray-700 font-medium">{entry.satisfaction_rate}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="px-6 py-4 text-sm text-gray-500 text-center">
              No feedback data yet. Users can rate AI responses with thumbs up/down in the chat.
            </div>
          )}
        </div>
      </div>
      {/* Model Performance Comparison */}
      {performance && (
        <div>
          <div className="mt-8 flex items-center gap-4">
            <label className="text-sm text-gray-600">Performance period:</label>
            <select
              value={perfDays}
              onChange={(e) => setPerfDays(Number(e.target.value))}
              className="border border-gray-300 rounded px-2 py-1 text-sm bg-white text-gray-700"
            >
              <option value={1}>Last 24 hours</option>
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </div>
          <ModelPerformanceSection performance={performance} />
        </div>
      )}
    </div>
  )
}
