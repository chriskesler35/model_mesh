'use client'

export const dynamic = 'force-dynamic'
export const revalidate = 0

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import { renderMarkdown } from '@/lib/markdown'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'

// ─── Types ────────────────────────────────────────────────────────────────────
interface PhaseDef {
  name: string
  role: string
  model?: string
  default_model?: string
  artifact_type: 'json' | 'md' | 'code'
  system_prompt?: string
}

interface PhaseRun {
  id: string
  pipeline_id: string
  phase_index: number
  phase_name: string
  agent_role: string
  model_id?: string
  status: 'pending' | 'running' | 'awaiting_approval' | 'approved' | 'rejected' | 'failed' | 'skipped'
  input_context?: any
  output_artifact?: {
    type: 'json' | 'md' | 'code'
    data?: any
    content?: string
    files?: Array<{ path: string; content: string }>
    raw?: string
    files_written_to_disk?: string[]
  } | null
  raw_response?: string
  user_feedback?: string
  input_tokens?: number
  output_tokens?: number
  started_at?: string
  completed_at?: string
  created_at?: string
}

interface Pipeline {
  id: string
  session_id: string
  method_id: string
  phases: PhaseDef[]
  current_phase_index: number
  status: 'pending' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled'
  auto_approve: boolean
  initial_task: string
  created_at?: string
  completed_at?: string
  phase_runs?: PhaseRun[]
}

// ─── Role → avatar mapping ────────────────────────────────────────────────────
const ROLE_AVATARS: Record<string, { icon: string; color: string }> = {
  'Business Analyst':       { icon: '🔍', color: 'from-blue-400 to-indigo-500' },
  'Product Manager':        { icon: '📋', color: 'from-emerald-400 to-teal-500' },
  'Software Architect':     { icon: '🏛️', color: 'from-purple-400 to-indigo-500' },
  'Software Engineer':      { icon: '💻', color: 'from-blue-500 to-cyan-500' },
  'Code Reviewer':          { icon: '👀', color: 'from-amber-400 to-orange-500' },
  'QA Engineer':            { icon: '🧪', color: 'from-green-400 to-emerald-500' },
  'Rapid Prototyper':       { icon: '⚡', color: 'from-orange-400 to-red-500' },
  'Smoke Tester':           { icon: '💨', color: 'from-teal-400 to-cyan-500' },
  'Release Engineer':       { icon: '🚀', color: 'from-indigo-400 to-purple-500' },
  'Research Analyst':       { icon: '📚', color: 'from-violet-400 to-purple-500' },
  'Solution Planner':       { icon: '🗺️', color: 'from-sky-400 to-blue-500' },
  'Implementation Executor':{ icon: '⚙️', color: 'from-gray-500 to-slate-600' },
  'Solution Validator':     { icon: '✅', color: 'from-green-500 to-emerald-600' },
}

const STATUS_STYLE: Record<string, { bg: string; text: string; ring: string; label: string }> = {
  pending:            { bg: 'bg-gray-50 dark:bg-gray-800',         text: 'text-gray-500',   ring: 'ring-gray-200 dark:ring-gray-700',   label: 'Pending' },
  running:            { bg: 'bg-blue-50 dark:bg-blue-900/20',      text: 'text-blue-600',   ring: 'ring-blue-300 dark:ring-blue-700',   label: 'Running' },
  awaiting_approval:  { bg: 'bg-amber-50 dark:bg-amber-900/20',    text: 'text-amber-700',  ring: 'ring-amber-300 dark:ring-amber-700', label: 'Awaiting approval' },
  approved:           { bg: 'bg-green-50 dark:bg-green-900/20',    text: 'text-green-700',  ring: 'ring-green-300 dark:ring-green-700', label: 'Approved' },
  rejected:           { bg: 'bg-red-50 dark:bg-red-900/20',        text: 'text-red-700',    ring: 'ring-red-300 dark:ring-red-700',     label: 'Rejected (re-running)' },
  failed:             { bg: 'bg-red-50 dark:bg-red-900/20',        text: 'text-red-700',    ring: 'ring-red-300 dark:ring-red-700',     label: 'Failed' },
  skipped:            { bg: 'bg-gray-100 dark:bg-gray-800',        text: 'text-gray-500',   ring: 'ring-gray-300 dark:ring-gray-600',   label: 'Skipped' },
}

// ─── Artifact viewer ──────────────────────────────────────────────────────────
function ArtifactViewer({ artifact }: { artifact: PhaseRun['output_artifact'] }) {
  const [copied, setCopied] = useState(false)
  if (!artifact) return <div className="text-sm text-gray-400 italic">No artifact yet.</div>

  const copy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  if (artifact.type === 'json' && artifact.data) {
    const json = JSON.stringify(artifact.data, null, 2)
    return (
      <div className="relative">
        <button onClick={() => copy(json)}
          className="absolute top-2 right-2 z-10 text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700">
          {copied ? '✓' : '📋'}
        </button>
        <pre className="bg-gray-900 text-green-300 rounded-lg p-3 text-xs overflow-auto max-h-96 font-mono leading-relaxed">
          {json}
        </pre>
      </div>
    )
  }

  if (artifact.type === 'code' && artifact.files && artifact.files.length > 0) {
    return (
      <div className="space-y-3">
        {artifact.files_written_to_disk && artifact.files_written_to_disk.length > 0 && (
          <div className="text-xs text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 px-3 py-1.5 rounded-lg">
            ✓ {artifact.files_written_to_disk.length} file(s) written to disk
          </div>
        )}
        {artifact.files.map((f, i) => (
          <details key={i} className="bg-gray-900 rounded-lg overflow-hidden">
            <summary className="px-3 py-2 text-xs font-mono text-gray-200 cursor-pointer hover:bg-gray-800 flex items-center justify-between">
              <span>📄 {f.path}</span>
              <span className="text-gray-500">{f.content.split('\n').length} lines</span>
            </summary>
            <pre className="px-3 py-2 text-xs text-green-300 overflow-auto max-h-80 border-t border-gray-800">{f.content}</pre>
          </details>
        ))}
      </div>
    )
  }

  if (artifact.type === 'md' && artifact.content) {
    return (
      <div className="prose prose-sm dark:prose-invert max-w-none text-sm text-gray-700 dark:text-gray-200"
           dangerouslySetInnerHTML={{ __html: `<p class="mb-2">${renderMarkdown(artifact.content)}</p>` }} />
    )
  }

  // Fallback: show raw
  return (
    <div className="relative">
      <button onClick={() => copy(artifact.raw || '')}
        className="absolute top-2 right-2 z-10 text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700">
        {copied ? '✓' : '📋'}
      </button>
      <pre className="bg-gray-900 text-gray-200 rounded-lg p-3 text-xs overflow-auto max-h-80 whitespace-pre-wrap">
        {artifact.raw || '(empty)'}
      </pre>
    </div>
  )
}

// ─── Phase Card ───────────────────────────────────────────────────────────────
function PhaseCard({
  phase, run, isCurrent, onOpenApproval, onViewArtifact,
}: {
  phase: PhaseDef
  run: PhaseRun | null
  isCurrent: boolean
  onOpenApproval: (run: PhaseRun) => void
  onViewArtifact: (run: PhaseRun) => void
}) {
  const avatar = ROLE_AVATARS[phase.role] || { icon: '🤖', color: 'from-gray-400 to-gray-600' }
  const status = run?.status || 'pending'
  const style = STATUS_STYLE[status] || STATUS_STYLE.pending
  const isRunning = status === 'running'
  const awaitingApproval = status === 'awaiting_approval'
  const tokens = (run?.input_tokens || 0) + (run?.output_tokens || 0)

  return (
    <div className={`relative rounded-xl border-2 bg-white dark:bg-gray-800 overflow-hidden transition-all
                     ${isCurrent ? `ring-4 ${style.ring} shadow-lg` : 'ring-1 ring-gray-200 dark:ring-gray-700'}`}>
      {/* Header */}
      <div className={`px-4 py-3 border-b border-gray-200 dark:border-gray-700 ${style.bg}`}>
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${avatar.color} flex items-center justify-center text-lg flex-shrink-0
                          ${isRunning ? 'animate-pulse' : ''}`}>
            {avatar.icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-900 dark:text-white truncate">{phase.name}</span>
              <span className={`text-[10px] font-medium uppercase tracking-wider px-1.5 py-0.5 rounded ${style.text}`}>
                {style.label}
              </span>
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{phase.role}</div>
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
          <span className="font-mono truncate">{phase.model || phase.default_model || '—'}</span>
          {tokens > 0 && <span>{tokens.toLocaleString()} tok</span>}
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {status === 'pending' && <div className="text-xs text-gray-400 italic">Waiting for earlier phases…</div>}

        {isRunning && (
          <div className="flex items-center gap-2 text-xs text-blue-600 dark:text-blue-400">
            <div className="flex gap-1">
              {[0, 1, 2].map(i => (
                <div key={i} className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce"
                     style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
            <span>Working…</span>
          </div>
        )}

        {status === 'failed' && (
          <div className="text-xs text-red-600 dark:text-red-400">Phase failed. See backend logs.</div>
        )}

        {status === 'skipped' && (
          <div className="text-xs text-gray-500 dark:text-gray-400">Skipped by user.</div>
        )}

        {(status === 'awaiting_approval' || status === 'approved') && run?.output_artifact && (
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-400 font-semibold mb-1.5">
              Artifact ({run.output_artifact.type})
            </div>
            <button onClick={() => onViewArtifact(run)}
              className="w-full px-3 py-2 text-xs font-semibold rounded-lg bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 transition-colors flex items-center justify-center gap-2">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              View full artifact
            </button>
          </div>
        )}

        {run?.user_feedback && status === 'rejected' && (
          <div className="mt-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
            <span className="font-semibold">Rejection feedback:</span> {run.user_feedback}
          </div>
        )}
      </div>

      {/* Action bar */}
      {awaitingApproval && run && (
        <div className="px-4 py-2 bg-amber-100 dark:bg-amber-900/30 border-t border-amber-200 dark:border-amber-800">
          <button onClick={() => onOpenApproval(run)}
            className="w-full text-xs font-semibold text-amber-800 dark:text-amber-200 hover:text-amber-900 py-1.5">
            👁 Review & approve →
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Approval Modal ───────────────────────────────────────────────────────────
function ApprovalModal({
  run, phase, onClose, onApprove, onReject, onSkip,
}: {
  run: PhaseRun
  phase: PhaseDef | undefined
  onClose: () => void
  onApprove: (feedback?: string) => Promise<void>
  onReject: (feedback: string) => Promise<void>
  onSkip: (reason?: string) => Promise<void>
}) {
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState<'approve' | 'reject' | 'skip' | null>(null)

  const handleApprove = async () => {
    setBusy('approve')
    try { await onApprove(feedback || undefined); onClose() } finally { setBusy(null) }
  }
  const handleReject = async () => {
    if (!feedback.trim()) { alert('Rejection requires feedback — tell the agent what to fix.'); return }
    setBusy('reject')
    try { await onReject(feedback); onClose() } finally { setBusy(null) }
  }
  const handleSkip = async () => {
    setBusy('skip')
    try { await onSkip(feedback || undefined); onClose() } finally { setBusy(null) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-4xl max-h-[90vh] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
              Review: {run.phase_name} <span className="text-gray-400">({run.agent_role})</span>
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {run.input_tokens?.toLocaleString() || 0} in + {run.output_tokens?.toLocaleString() || 0} out tokens · {run.model_id}
            </p>
          </div>
          <button onClick={onClose} disabled={busy !== null} className="text-gray-400 hover:text-gray-600 disabled:opacity-30">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-auto px-6 py-4 space-y-4">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-gray-400 font-semibold mb-2">Artifact</div>
            <ArtifactViewer artifact={run.output_artifact} />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
              Feedback (required for reject, optional for approve/skip)
            </label>
            <textarea value={feedback} onChange={e => setFeedback(e.target.value)} rows={3}
              placeholder="e.g. The architect's data model is missing the 'user_id' foreign key on orders..."
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
          </div>
        </div>

        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-800 flex gap-3 justify-end flex-shrink-0">
          <button onClick={handleSkip} disabled={busy !== null}
            className="px-4 py-2 text-sm font-medium rounded-lg text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40">
            ⏭ Skip phase
          </button>
          <button onClick={handleReject} disabled={busy !== null}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-red-500 hover:bg-red-600 text-white disabled:opacity-40">
            {busy === 'reject' ? 'Rejecting…' : '✗ Reject & re-run'}
          </button>
          <button onClick={handleApprove} disabled={busy !== null}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white disabled:opacity-40">
            {busy === 'approve' ? 'Approving…' : '✓ Approve & continue'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Save as Template Dialog ──────────────────────────────────────────────────
function SaveAsTemplateDialog({ pipelineId, onClose }: { pipelineId: string; onClose: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [includeSystemPrompts, setIncludeSystemPrompts] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const handleSave = async () => {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/v1/workbench/pipelines/${pipelineId}/save-as-template`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify({ name: name.trim(), description: description.trim() || null, include_system_prompts: includeSystemPrompts }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      setSuccess(true)
      setTimeout(onClose, 1500)
    } catch (e: any) {
      setError(e.message || 'Failed to save template')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">Save as Method Template</h2>
          <p className="text-xs text-gray-500 mt-0.5">Create a reusable method from this pipeline&apos;s configuration</p>
        </div>
        <div className="px-6 py-4 space-y-4">
          {success ? (
            <div className="text-center py-4">
              <div className="text-3xl mb-2">✅</div>
              <div className="text-sm font-semibold text-green-700 dark:text-green-400">Template saved!</div>
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">Template Name *</label>
                <input type="text" value={name} onChange={e => setName(e.target.value)} maxLength={200}
                  placeholder="e.g. My Custom Pipeline"
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400" />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">Description</label>
                <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2}
                  placeholder="What this template is good for..."
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 resize-none" />
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={includeSystemPrompts} onChange={e => setIncludeSystemPrompts(e.target.checked)}
                  className="rounded border-gray-300 text-teal-600 focus:ring-teal-400" />
                <span className="text-sm text-gray-700 dark:text-gray-300">Include system prompts from this run</span>
              </label>
              {error && <div className="text-xs text-red-600 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</div>}
            </>
          )}
        </div>
        {!success && (
          <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-800 flex gap-3 justify-end">
            <button onClick={onClose} disabled={saving}
              className="px-4 py-2 text-sm font-medium rounded-lg text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40">
              Cancel
            </button>
            <button onClick={handleSave} disabled={saving || !name.trim()}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-teal-500 hover:bg-teal-600 text-white disabled:opacity-40">
              {saving ? 'Saving…' : 'Save Template'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function PipelinePage() {
  const params = useParams()
  const router = useRouter()
  const pipelineId = Array.isArray(params?.id) ? params.id[0] : params?.id as string

  const [pipeline, setPipeline] = useState<Pipeline | null>(null)
  const [phaseRuns, setPhaseRuns] = useState<PhaseRun[]>([])
  const [loading, setLoading] = useState(true)
  const [approvalRun, setApprovalRun] = useState<PhaseRun | null>(null)
  const [viewArtifactRun, setViewArtifactRun] = useState<PhaseRun | null>(null)
  const [showSaveTemplate, setShowSaveTemplate] = useState(false)

  // Escape closes the read-only artifact modal
  useEffect(() => {
    if (!viewArtifactRun) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') setViewArtifactRun(null) }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [viewArtifactRun])
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  // Derive: most recent run per phase_index (handles re-runs after rejection)
  const runsByIndex: Record<number, PhaseRun> = {}
  for (const r of phaseRuns) {
    const existing = runsByIndex[r.phase_index]
    if (!existing || new Date(r.created_at || 0) > new Date(existing.created_at || 0)) {
      runsByIndex[r.phase_index] = r
    }
  }

  const refetch = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/workbench/pipelines/${pipelineId}`, { headers: AUTH_HEADERS })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setPipeline(data)
      setPhaseRuns(data.phase_runs || [])
      setLoading(false)
    } catch (e: any) {
      setError(e.message || 'Failed to load pipeline')
      setLoading(false)
    }
  }, [pipelineId])

  // Initial fetch
  useEffect(() => {
    if (!pipelineId) return
    refetch()
  }, [pipelineId, refetch])

  // SSE subscription
  useEffect(() => {
    if (!pipelineId) return
    const es = new EventSource(`${API_BASE}/v1/workbench/pipelines/${pipelineId}/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data)
        if (evt.type === 'ping') return
        if (evt.type === 'init') {
          setPipeline(evt.payload)
          setPhaseRuns(evt.payload.phase_runs || [])
          return
        }
        // Any other event → refetch state to get the latest
        refetch()
      } catch {}
    }
    es.onerror = () => { /* browser retries automatically */ }

    return () => { es.close(); esRef.current = null }
  }, [pipelineId, refetch])

  const approve = async (feedback?: string) => {
    await fetch(`${API_BASE}/v1/workbench/pipelines/${pipelineId}/approve`, {
      method: 'POST', headers: AUTH_HEADERS,
      body: JSON.stringify({ feedback: feedback || null }),
    })
    refetch()
  }
  const reject = async (feedback: string) => {
    await fetch(`${API_BASE}/v1/workbench/pipelines/${pipelineId}/reject`, {
      method: 'POST', headers: AUTH_HEADERS,
      body: JSON.stringify({ feedback }),
    })
    refetch()
  }
  const skip = async (reason?: string) => {
    await fetch(`${API_BASE}/v1/workbench/pipelines/${pipelineId}/skip`, {
      method: 'POST', headers: AUTH_HEADERS,
      body: JSON.stringify({ reason: reason || null }),
    })
    refetch()
  }
  const cancelPipeline = async () => {
    if (!confirm('Cancel this pipeline? Any running phase will be abandoned.')) return
    await fetch(`${API_BASE}/v1/workbench/pipelines/${pipelineId}/cancel`, {
      method: 'POST', headers: AUTH_HEADERS,
    })
    refetch()
  }
  const retryPipeline = async () => {
    await fetch(`${API_BASE}/v1/workbench/pipelines/${pipelineId}/retry`, {
      method: 'POST', headers: AUTH_HEADERS,
    })
    refetch()
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="flex gap-1.5">{[0,1,2].map(i =>
          <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}
        </div>
      </div>
    )
  }

  if (error || !pipeline) {
    return (
      <div className="text-center py-20">
        <div className="text-5xl mb-4">⚠️</div>
        <h3 className="text-lg font-semibold mb-2">Could not load pipeline</h3>
        <p className="text-sm text-gray-500 mb-4">{error || 'Pipeline not found'}</p>
        <button onClick={() => router.push('/workbench')} className="text-sm text-indigo-600 hover:underline">
          ← Back to workbench
        </button>
      </div>
    )
  }

  const statusBadge = STATUS_STYLE[pipeline.status] || STATUS_STYLE.pending
  const totalTokens = phaseRuns.reduce((sum, r) => sum + (r.input_tokens || 0) + (r.output_tokens || 0), 0)
  const currentPhaseRun = runsByIndex[pipeline.current_phase_index]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <button onClick={() => router.push('/workbench')} className="text-xs text-gray-400 hover:text-gray-600">← Workbench</button>
            <span className="text-gray-300">/</span>
            <span className="text-xs text-gray-500">Pipeline</span>
            <span className="text-xs uppercase font-semibold px-2 py-0.5 rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300">
              {pipeline.method_id}
            </span>
            <span className={`text-xs uppercase font-semibold px-2 py-0.5 rounded ${statusBadge.bg} ${statusBadge.text}`}>
              {statusBadge.label}
            </span>
            {pipeline.auto_approve && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                AUTO
              </span>
            )}
          </div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white leading-snug">{pipeline.initial_task}</h1>
          <div className="text-xs text-gray-500 mt-1">
            {pipeline.phases.length} phases · {totalTokens.toLocaleString()} tokens used
          </div>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          {pipeline.status === 'completed' && (
            <button onClick={() => setShowSaveTemplate(true)}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-teal-500 hover:bg-teal-600 text-white">
              💾 Save as Template
            </button>
          )}
          {(pipeline.status === 'failed' || pipeline.status === 'cancelled') && (
            <button onClick={retryPipeline}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white">
              ↻ Retry phase {pipeline.current_phase_index + 1}
            </button>
          )}
          {(pipeline.status === 'running' || pipeline.status === 'awaiting_approval' || pipeline.status === 'pending') && (
            <button onClick={cancelPipeline}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20">
              Cancel
            </button>
          )}
          <button onClick={refetch}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800">
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Awaiting-approval banner */}
      {pipeline.status === 'awaiting_approval' && currentPhaseRun && (
        <div className="rounded-xl border-2 border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 p-4 flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-amber-900 dark:text-amber-200">
              {currentPhaseRun.agent_role} is waiting for your review
            </div>
            <div className="text-xs text-amber-700 dark:text-amber-300 mt-0.5">
              Phase "{currentPhaseRun.phase_name}" complete · review the artifact and approve, reject with feedback, or skip
            </div>
          </div>
          <button onClick={() => setApprovalRun(currentPhaseRun)}
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-amber-500 hover:bg-amber-600 text-white">
            Review now →
          </button>
        </div>
      )}

      {/* Swim lanes */}
      <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${pipeline.phases.length}, minmax(240px, 1fr))` }}>
        {pipeline.phases.map((phase, idx) => (
          <PhaseCard
            key={idx}
            phase={phase}
            run={runsByIndex[idx] || null}
            isCurrent={idx === pipeline.current_phase_index && pipeline.status !== 'completed'}
            onOpenApproval={setApprovalRun}
            onViewArtifact={setViewArtifactRun}
          />
        ))}
      </div>

      {/* Approval modal */}
      {approvalRun && (
        <ApprovalModal
          run={approvalRun}
          phase={pipeline.phases[approvalRun.phase_index]}
          onClose={() => setApprovalRun(null)}
          onApprove={approve}
          onReject={reject}
          onSkip={skip}
        />
      )}

      {/* View artifact modal (read-only, full-screen) */}
      {viewArtifactRun && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
             onClick={() => setViewArtifactRun(null)}>
          <div className="w-full max-w-5xl max-h-[92vh] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
               onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between flex-shrink-0">
              <div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                  {viewArtifactRun.phase_name} <span className="text-gray-400">— {viewArtifactRun.agent_role}</span>
                </h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  {viewArtifactRun.input_tokens?.toLocaleString() || 0} in + {viewArtifactRun.output_tokens?.toLocaleString() || 0} out tokens · {viewArtifactRun.model_id} · {viewArtifactRun.output_artifact?.type || 'unknown'}
                </p>
              </div>
              <button onClick={() => setViewArtifactRun(null)} className="text-gray-400 hover:text-gray-600">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6">
              <ArtifactViewer artifact={viewArtifactRun.output_artifact} />
            </div>
          </div>
        </div>
      )}

      {/* Save as Template dialog */}
      {showSaveTemplate && <SaveAsTemplateDialog
        pipelineId={pipelineId}
        onClose={() => setShowSaveTemplate(false)}
      />}
    </div>
  )
}
