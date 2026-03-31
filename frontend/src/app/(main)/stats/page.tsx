'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect } from 'react'

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

export default function StatsPage() {
  const [costs, setCosts] = useState<CostSummary | null>(null)
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchStats() {
      try {
        const [costsRes, usageRes] = await Promise.all([
          fetch(`${API_BASE}/v1/stats/costs?days=7`, {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json()),
          fetch(`${API_BASE}/v1/stats/usage?days=7`, {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json())
        ])
        setCosts(costsRes)
        setUsage(usageRes)
      } catch (e) {
        console.error('Failed to fetch stats:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchStats()
  }, [])

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
    </div>
  )
}