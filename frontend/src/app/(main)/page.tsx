'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'

interface Persona {
  id: string
  name: string
  description?: string
  is_default: boolean
  memory_enabled: boolean
  max_memory_messages: number
}

interface Model {
  id: string
  model_id: string
  display_name?: string
  provider_name?: string
  is_active: boolean
  context_window?: number
  cost_per_1m_input: number
  cost_per_1m_output: number
}

interface Conversation {
  id: string
  title?: string
  message_count?: number
  last_message_at?: string
}

function StatCard({ label, value, sub, href }: { label: string; value: string | number; sub?: string; href?: string }) {
  const inner = (
    <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden group hover:shadow-md hover:border-orange-300 dark:hover:border-orange-500 transition-all">
      <div className="px-5 py-5">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{label}</p>
        <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-white">{value}</p>
      </div>
      {sub && (
        <div className="px-5 py-3 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-100 dark:border-gray-700">
          <p className="text-xs font-medium text-orange-600 dark:text-orange-400 group-hover:underline">{sub}</p>
        </div>
      )}
    </div>
  )
  return href ? <Link href={href}>{inner}</Link> : <div>{inner}</div>
}

function QuickAction({ href, icon, label, desc, external }: {
  href: string; icon: React.ReactNode; label: string; desc: string; external?: boolean
}) {
  const cls = "flex items-center gap-4 p-5 bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-orange-300 dark:hover:border-orange-500 transition-all"
  const content = (
    <>
      <div className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-xl bg-orange-50 dark:bg-orange-900/20 text-orange-500">
        {icon}
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-900 dark:text-white">{label}</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{desc}</p>
      </div>
    </>
  )
  if (external) return <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>{content}</a>
  return <Link href={href} className={cls}>{content}</Link>
}

export default function Home() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      try {
        const [personasRes, modelsRes, conversationsRes] = await Promise.all([
          api.getPersonas(),
          api.getModels(),
          api.getConversations(),
        ])
        setPersonas(personasRes.data)
        setModels(modelsRes.data)
        setConversations(conversationsRes.data)
      } catch (e) {
        console.error('Failed to fetch data:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const activeModels = models.filter(m => m.is_active)

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex gap-1.5">
          {[0,1,2].map(i => (
            <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Overview of your DevForgeAI gateway</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Personas" value={personas.length} sub="Manage personas →" href="/personas" />
        <StatCard label="Models" value={models.length} sub={`${activeModels.length} active →`} href="/models" />
        <StatCard label="Conversations" value={conversations.length} sub="View history →" href="/conversations" />
        <StatCard label="Status" value="Healthy" sub="All systems operational" />
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-3">Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <QuickAction href="/chat" label="New Chat" desc="Start a conversation"
            icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>}
          />
          <QuickAction href="/personas/new" label="New Persona" desc="Create an AI persona"
            icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>}
          />
          <QuickAction href="/stats" label="View Stats" desc="Usage and cost tracking"
            icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>}
          />
          <QuickAction href="http://localhost:19000/docs" label="API Docs" desc="OpenAPI / Swagger" external
            icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>}
          />
        </div>
      </div>

      {/* Bottom grid — Personas + Models */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Personas */}
        {personas.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">Personas</h2>
              <Link href="/personas" className="text-xs text-orange-600 dark:text-orange-400 hover:underline">View all →</Link>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
              <ul className="divide-y divide-gray-100 dark:divide-gray-700">
                {personas.slice(0, 5).map(p => (
                  <li key={p.id}>
                    <Link href={`/personas/${p.id}`} className="flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{p.name}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">{p.description || 'No description'}</p>
                      </div>
                      <span className={`ml-3 flex-shrink-0 px-2 py-0.5 text-xs font-medium rounded-full ${
                        p.is_default
                          ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                      }`}>
                        {p.is_default ? 'Default' : 'Active'}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Models */}
        {models.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">Models</h2>
              <Link href="/models" className="text-xs text-orange-600 dark:text-orange-400 hover:underline">View all →</Link>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
              <ul className="divide-y divide-gray-100 dark:divide-gray-700">
                {models.slice(0, 5).map(m => (
                  <li key={m.id} className="flex items-center justify-between px-5 py-3.5">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{m.display_name || m.model_id}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 capitalize">{m.provider_name || 'Unknown'}</p>
                    </div>
                    <span className={`ml-3 flex-shrink-0 px-2 py-0.5 text-xs font-medium rounded-full ${
                      m.is_active
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                        : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                    }`}>
                      {m.is_active ? 'Active' : 'Off'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
