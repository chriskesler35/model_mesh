import Link from 'next/link'
import { api } from '@/lib/api'

async function getStats() {
  try {
    const [personasRes, modelsRes, conversationsRes] = await Promise.all([
      api.getPersonas(),
      api.getModels(),
      api.getConversations(),
    ])
    return {
      personas: personasRes.data,
      models: modelsRes.data,
      conversations: conversationsRes.data,
    }
  } catch (e) {
    console.error('Failed to fetch data:', e)
    return { personas: [], models: [], conversations: [] }
  }
}

export default async function Home() {
  const { personas, models, conversations } = await getStats()

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Overview of your AI gateway
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Personas
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {personas.length}
            </dd>
          </div>
          <div className="bg-gray-50 px-4 py-4 sm:px-6">
            <Link href="/personas" className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
              View all →
            </Link>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Models
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {models.length}
            </dd>
          </div>
          <div className="bg-gray-50 px-4 py-4 sm:px-6">
            <Link href="/models" className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
              View all →
            </Link>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Conversations
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-gray-900">
              {conversations.length}
            </dd>
          </div>
          <div className="bg-gray-50 px-4 py-4 sm:px-6">
            <Link href="/conversations" className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
              View all →
            </Link>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <dt className="text-sm font-medium text-gray-500 truncate">
              Status
            </dt>
            <dd className="mt-1 text-3xl font-semibold text-green-600">
              Healthy
            </dd>
          </div>
          <div className="bg-gray-50 px-4 py-4 sm:px-6">
            <span className="text-sm text-gray-500">All systems operational</span>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Link
            href="/personas/new"
            className="relative flex items-center space-x-3 rounded-lg border border-gray-300 bg-white px-6 py-5 shadow-sm hover:border-indigo-400 hover:ring-1 hover:ring-indigo-400"
          >
            <div className="flex-shrink-0">
              <svg className="h-10 w-10 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <span className="absolute inset-0" aria-hidden="true" />
              <p className="text-sm font-medium text-gray-900">New Persona</p>
              <p className="text-sm text-gray-500 truncate">Create a new AI persona</p>
            </div>
          </Link>

          <Link
            href="/conversations"
            className="relative flex items-center space-x-3 rounded-lg border border-gray-300 bg-white px-6 py-5 shadow-sm hover:border-indigo-400 hover:ring-1 hover:ring-indigo-400"
          >
            <div className="flex-shrink-0">
              <svg className="h-10 w-10 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <span className="absolute inset-0" aria-hidden="true" />
              <p className="text-sm font-medium text-gray-900">New Chat</p>
              <p className="text-sm text-gray-500 truncate">Start a new conversation</p>
            </div>
          </Link>

          <Link
            href="/stats"
            className="relative flex items-center space-x-3 rounded-lg border border-gray-300 bg-white px-6 py-5 shadow-sm hover:border-indigo-400 hover:ring-1 hover:ring-indigo-400"
          >
            <div className="flex-shrink-0">
              <svg className="h-10 w-10 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <span className="absolute inset-0" aria-hidden="true" />
              <p className="text-sm font-medium text-gray-900">View Stats</p>
              <p className="text-sm text-gray-500 truncate">Usage and costs</p>
            </div>
          </Link>

          <a
            href="http://localhost:18800/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="relative flex items-center space-x-3 rounded-lg border border-gray-300 bg-white px-6 py-5 shadow-sm hover:border-indigo-400 hover:ring-1 hover:ring-indigo-400"
          >
            <div className="flex-shrink-0">
              <svg className="h-10 w-10 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-900">API Docs</p>
              <p className="text-sm text-gray-500 truncate">OpenAPI / Swagger</p>
            </div>
          </a>
        </div>
      </div>

      {/* Recent Personas */}
      {personas.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Personas</h2>
          <div className="bg-white shadow overflow-hidden sm:rounded-md">
            <ul className="divide-y divide-gray-200">
              {personas.slice(0, 5).map((persona) => (
                <li key={persona.id}>
                  <Link href={`/personas/${persona.id}`} className="block hover:bg-gray-50">
                    <div className="px-4 py-4 sm:px-6">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-indigo-600 truncate">
                          {persona.name}
                        </p>
                        <div className="ml-2 flex-shrink-0 flex">
                          <p className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                            persona.is_default 
                              ? 'bg-green-100 text-green-800' 
                              : 'bg-gray-100 text-gray-800'
                          }`}>
                            {persona.is_default ? 'Default' : 'Active'}
                          </p>
                        </div>
                      </div>
                      <div className="mt-2 sm:flex sm:justify-between">
                        <div className="sm:flex">
                          <p className="text-sm text-gray-500">
                            {persona.description || 'No description'}
                          </p>
                        </div>
                        <div className="mt-2 sm:mt-0">
                          <p className="text-sm text-gray-500">
                            Memory: {persona.memory_enabled ? `${persona.max_memory_messages} messages` : 'Disabled'}
                          </p>
                        </div>
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Models Overview */}
      {models.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Available Models</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {models.map((model) => (
              <div key={model.id} className="bg-white shadow rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-gray-900">{model.display_name || model.model_id}</h3>
                  <span className={`px-2 py-1 text-xs rounded-full ${
                    model.is_active 
                      ? 'bg-green-100 text-green-800' 
                      : 'bg-red-100 text-red-800'
                  }`}>
                    {model.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <p className="mt-1 text-xs text-gray-500">{model.provider_name || 'Unknown'}</p>
                <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
                  <span>Context: {model.context_window?.toLocaleString() || 'N/A'} tokens</span>
                  <span>
                    ${model.cost_per_1m_input}/{model.cost_per_1m_output} per 1M
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}