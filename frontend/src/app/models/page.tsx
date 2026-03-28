import { api } from '@/lib/api'

async function getModels() {
  try {
    const res = await api.getModels(100, 0)
    return res.data
  } catch (e) {
    console.error('Failed to fetch models:', e)
    return []
  }
}

function formatCost(cost: number): string {
  if (cost === 0) return 'Free'
  return `$${cost.toFixed(4)}/1M`
}

function formatContext(tokens: number | undefined): string {
  if (!tokens) return 'N/A'
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(0)}K`
  return tokens.toString()
}

export default async function ModelsPage() {
  const models = await getModels()

  // Group models by provider
  const grouped = models.reduce((acc, model) => {
    const provider = model.provider_name || 'Unknown'
    if (!acc[provider]) acc[provider] = []
    acc[provider].push(model)
    return acc
  }, {} as Record<string, typeof models>)

  return (
    <div>
      <div className="sm:flex sm:items-center sm:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Models</h1>
          <p className="mt-1 text-sm text-gray-500">
            Available AI models from all providers
          </p>
        </div>
      </div>

      {Object.entries(grouped).map(([provider, providerModels]) => (
        <div key={provider} className="mb-8">
          <h2 className="text-lg font-medium text-gray-900 mb-4 capitalize">{provider}</h2>
          <div className="bg-white shadow overflow-hidden sm:rounded-md">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Context
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Input Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Output Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Capabilities
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {providerModels.map((model) => (
                  <tr key={model.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">
                        {model.display_name || model.model_id}
                      </div>
                      <div className="text-sm text-gray-500">{model.model_id}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-sm text-gray-900">
                        {formatContext(model.context_window)} tokens
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatCost(model.cost_per_1m_input)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatCost(model.cost_per_1m_output)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(model.capabilities || {}).map(([key, value]) => (
                          value && (
                            <span
                              key={key}
                              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
                            >
                              {key}
                            </span>
                          )
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        model.is_active
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}>
                        {model.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {models.length === 0 && (
        <div className="text-center py-12">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 15v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
          </svg>
          <h3 className="mt-2 text-sm font-medium text-gray-900">No models</h3>
          <p className="mt-1 text-sm text-gray-500">
            Models are configured via the database. Check your seed data.
          </p>
        </div>
      )}
    </div>
  )
}