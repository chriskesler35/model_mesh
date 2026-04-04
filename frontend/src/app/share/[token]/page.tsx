'use client'

import { getApiBase } from '@/lib/config'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'

interface ShareMeta {
  token: string
  access_level: string
  expires_at: string | null
  created_by: string
}

interface Message {
  id: string
  role: string
  content: string
  image_url: string | null
  created_at: string
}

interface ConversationData {
  id: string
  title: string
  created_at: string
  messages: Message[]
}

interface ShareResponse {
  share: ShareMeta
  resource_type: 'conversation' | 'project' | 'workspace'
  data: any
}

export default function SharedResourcePage() {
  const params = useParams()
  const token = params?.token as string
  const [status, setStatus] = useState<'loading' | 'ok' | 'expired' | 'not_found' | 'error'>('loading')
  const [payload, setPayload] = useState<ShareResponse | null>(null)
  const [errMsg, setErrMsg] = useState('')

  useEffect(() => {
    if (!token) return
    fetch(`${getApiBase()}/v1/share/${token}`)
      .then(async r => {
        if (r.status === 410) { setStatus('expired'); return }
        if (r.status === 404) { setStatus('not_found'); return }
        if (!r.ok) {
          const e = await r.json().catch(() => ({}))
          setErrMsg(e?.detail || `Load failed (${r.status})`)
          setStatus('error')
          return
        }
        const data = await r.json()
        setPayload(data)
        setStatus('ok')
      })
      .catch(e => { setErrMsg(e.message); setStatus('error') })
  }, [token])

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="flex gap-1.5">
          {[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}
        </div>
      </div>
    )
  }

  if (status === 'not_found') {
    return <ErrorState icon="🔗" title="Link not found" message="This share link may have been revoked or never existed." />
  }
  if (status === 'expired') {
    return <ErrorState icon="⏱️" title="Link expired" message="This share link has expired. Ask the owner to create a new one." />
  }
  if (status === 'error') {
    return <ErrorState icon="⚠️" title="Could not load" message={errMsg} />
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Shared banner */}
      <div className="bg-orange-500 text-white text-center text-xs py-2 px-4">
        🔗 Shared {payload!.resource_type} · view-only · shared by {payload!.share.created_by}
        {payload!.share.expires_at && (
          <span className="ml-2 opacity-80">
            · expires {new Date(payload!.share.expires_at).toLocaleDateString()}
          </span>
        )}
      </div>

      <div className="max-w-4xl mx-auto px-4 py-8">
        {payload!.resource_type === 'conversation' && (
          <ConversationView data={payload!.data as ConversationData} />
        )}
        {payload!.resource_type === 'project' && (
          <ProjectView data={payload!.data} />
        )}
        {payload!.resource_type === 'workspace' && (
          <WorkspaceView data={payload!.data} />
        )}
      </div>

      <div className="text-center text-xs text-gray-400 pb-6">
        Powered by DevForgeAI
      </div>
    </div>
  )
}

function ErrorState({ icon, title, message }: { icon: string; title: string; message: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8 text-center">
        <div className="text-5xl mb-4">{icon}</div>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">{title}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">{message}</p>
      </div>
    </div>
  )
}

function ConversationView({ data }: { data: ConversationData }) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">
        {data.title || 'Untitled conversation'}
      </h1>
      <p className="text-xs text-gray-400 mb-6">
        {data.messages.length} messages · {new Date(data.created_at).toLocaleDateString()}
      </p>
      <div className="space-y-4">
        {data.messages.map(m => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
              m.role === 'user'
                ? 'bg-orange-500 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white border border-gray-200 dark:border-gray-700'
            }`}>
              <div className="text-xs opacity-60 mb-1">{m.role}</div>
              <div className="text-sm whitespace-pre-wrap">{m.content}</div>
              {m.image_url && (
                <img
                  src={m.image_url.startsWith('http') ? m.image_url : `${getApiBase()}${m.image_url}`}
                  alt=""
                  className="mt-2 rounded-lg max-w-full"
                />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ProjectView({ data }: { data: any }) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">{data.name}</h1>
      {data.description && <p className="text-sm text-gray-500 mb-4">{data.description}</p>}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-2 text-sm">
        <Field label="Path" value={data.path} mono />
        <Field label="Template" value={data.template} />
        <Field label="Sandbox" value={data.sandbox_mode} />
        <Field label="Created" value={new Date(data.created_at).toLocaleString()} />
      </div>
    </div>
  )
}

function WorkspaceView({ data }: { data: any }) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">{data.name}</h1>
      {data.description && <p className="text-sm text-gray-500 mb-4">{data.description}</p>}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-2 text-sm">
        <Field label="Projects" value={`${data.project_ids?.length || 0} linked`} />
        <Field label="Members" value={`${data.member_ids?.length || 0} collaborators`} />
        <Field label="Created" value={new Date(data.created_at).toLocaleString()} />
      </div>
    </div>
  )
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-right ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}
