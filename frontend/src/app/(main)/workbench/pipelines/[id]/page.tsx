'use client'

export const dynamic = 'force-dynamic'
export const revalidate = 0

import { getApiBase, getAuthHeaders } from '@/lib/config'
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
  depends_on?: string[]
  phase_type?: 'standard' | 'branch'
  branch_condition?: string
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
  retry_count?: number
  branch_result?: string
  branch_taken?: string
}

interface Pipeline {
  id: string
  session_id: string
  method_id: string
  phases: PhaseDef[]
  current_phase_index: number
  status: 'pending' | 'running' | 'paused' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled'
  auto_approve: boolean
  initial_task: string
  created_at?: string
  completed_at?: string
  phase_runs?: PhaseRun[]
}

interface PipelineEvent {
  type: string
  payload?: Record<string, any>
  ts?: string
}

interface ModelOption {
  id: string
  model_id: string
  display_name?: string
  provider_name?: string
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
  paused:             { bg: 'bg-slate-100 dark:bg-slate-800',      text: 'text-slate-700',  ring: 'ring-slate-300 dark:ring-slate-600', label: 'Paused' },
  awaiting_approval:  { bg: 'bg-amber-50 dark:bg-amber-900/20',    text: 'text-amber-700',  ring: 'ring-amber-300 dark:ring-amber-700', label: 'Awaiting approval' },
  approved:           { bg: 'bg-green-50 dark:bg-green-900/20',    text: 'text-green-700',  ring: 'ring-green-300 dark:ring-green-700', label: 'Approved' },
  rejected:           { bg: 'bg-red-50 dark:bg-red-900/20',        text: 'text-red-700',    ring: 'ring-red-300 dark:ring-red-700',     label: 'Rejected (re-running)' },
  failed:             { bg: 'bg-red-50 dark:bg-red-900/20',        text: 'text-red-700',    ring: 'ring-red-300 dark:ring-red-700',     label: 'Failed' },
  skipped:            { bg: 'bg-gray-100 dark:bg-gray-800',        text: 'text-gray-500',   ring: 'ring-gray-300 dark:ring-gray-600',   label: 'Skipped' },
}

const EVENT_REFRESH_TYPES = new Set([
  'pipeline_created',
  'phase_started',
  'phase_completed',
  'phase_failed',
  'awaiting_approval',
  'phase_skipped',
  'phase_branch',
  'phase_retry',
  'phase_retry_exhausted',
  'phase_model_changed',
  'pipeline_done',
  'files_written',
])

function makeEventKey(evt: PipelineEvent) {
  const payload = evt.payload || {}
  return [
    evt.ts || '',
    evt.type || '',
    payload.phase_run_id || '',
    payload.phase_index ?? '',
    payload.command_id || '',
    payload.message || '',
    payload.error || '',
  ].join('|')
}

function formatEventTime(ts?: string) {
  if (!ts) return 'now'
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return 'now'
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function describeEvent(evt: PipelineEvent, phases?: PhaseDef[]) {
  const payload = evt.payload || {}
  const phaseName = payload.phase_name || (typeof payload.phase_index === 'number' ? phases?.[payload.phase_index]?.name : undefined) || 'Phase'

  switch (evt.type) {
    case 'pipeline_created':
      return { tone: 'info', title: 'Pipeline created', detail: `${payload.phases?.length || 0} phases queued.` }
    case 'phase_started':
      return { tone: 'info', title: `${phaseName} started`, detail: `${payload.agent_role || 'Agent'} using ${payload.model_id || 'the selected model'}.` }
    case 'phase_thinking':
      return { tone: 'info', title: phaseName, detail: payload.message || 'Agent is working.' }
    case 'phase_progress':
      return { tone: 'info', title: `${phaseName} streaming`, detail: `${Number(payload.chars || 0).toLocaleString()} characters received.` }
    case 'phase_completed':
      return {
        tone: payload.status === 'approved' ? 'success' : 'info',
        title: `${phaseName} completed`,
        detail: payload.status === 'approved' ? 'Auto-approved and moving to the next step.' : 'Ready for your review.',
      }
    case 'awaiting_approval':
      return { tone: 'warning', title: 'Waiting for review', detail: payload.message || `${phaseName} is awaiting approval.` }
    case 'phase_failed':
      return {
        tone: 'error',
        title: `${phaseName} failed`,
        detail: payload.error || (payload.model_id ? `The selected model (${payload.model_id}) failed before producing an artifact.` : 'This phase failed before producing an artifact.'),
      }
    case 'phase_retry':
      return { tone: 'warning', title: `${phaseName} retrying`, detail: payload.message || 'Retrying with fresh guidance.' }
    case 'phase_retry_exhausted':
      return { tone: 'warning', title: `${phaseName} needs help`, detail: payload.message || 'Retry limit reached.' }
    case 'pipeline_retry': {
      const retriedNames = Array.isArray(payload.retried_phase_names) ? payload.retried_phase_names.filter(Boolean) : []
      const title = retriedNames.length === 1 ? `${retriedNames[0]} retrying` : 'Retrying failed phases'
      return {
        tone: 'warning',
        title,
        detail: payload.message || (retriedNames.length > 0 ? retriedNames.join(', ') : 'Retrying failed phases.'),
      }
    }
    case 'phase_model_changed':
      return {
        tone: 'warning',
        title: `${phaseName} model changed`,
        detail: payload.message || `Switched to ${payload.model_id || 'a new model'} and restarted the phase.`,
      }
    case 'phase_skipped':
      return { tone: 'warning', title: `${phaseName} skipped`, detail: payload.reason || 'Skipped by user or branch logic.' }
    case 'phase_branch':
      return { tone: 'info', title: `${phaseName} routed`, detail: `Continuing down "${payload.target || 'next'}".` }
    case 'files_written':
      return { tone: 'success', title: 'Files written', detail: `${payload.files?.length || 0} file(s) saved to the project.` }
    case 'command_awaiting_approval':
      return { tone: 'warning', title: 'Command needs approval', detail: payload.command || 'A command is waiting for approval.' }
    case 'command_running':
      return { tone: 'info', title: 'Command running', detail: payload.command || 'Executing command.' }
    case 'command_completed':
      return {
        tone: payload.exit_code === 0 ? 'success' : 'error',
        title: payload.exit_code === 0 ? 'Command completed' : 'Command failed',
        detail: payload.command || `Exit code ${payload.exit_code ?? 'unknown'}.`,
      }
    case 'warning':
      return { tone: 'warning', title: 'Warning', detail: payload.message || 'Something needs attention.' }
    case 'info':
      return { tone: 'info', title: 'Update', detail: payload.message || 'Pipeline update.' }
    case 'user_message':
      return {
        tone: 'info',
        title: 'Guidance sent',
        detail: payload.applies_to ? `${payload.message} (${payload.applies_to})` : payload.message || 'User guidance added.',
      }
    case 'pipeline_done':
      return {
        tone: payload.status === 'completed' ? 'success' : 'error',
        title: payload.status === 'completed' ? 'Pipeline finished' : 'Pipeline stopped',
        detail: payload.message || 'Pipeline run ended.',
      }
    default:
      return { tone: 'info', title: evt.type.replace(/_/g, ' '), detail: payload.message || payload.error || null }
  }
}

async function readApiPayload(res: Response) {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

function getApiErrorMessage(payload: any, status: number) {
  if (!payload) return `Request failed (${status})`
  if (typeof payload === 'string') return payload
  return payload.detail || payload.message || payload.error || `Request failed (${status})`
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
  phase, run, isCurrent, onOpenApproval, onViewArtifact, onChangeModel,
}: {
  phase: PhaseDef
  run: PhaseRun | null
  isCurrent: boolean
  onOpenApproval: (run: PhaseRun) => void
  onViewArtifact: (run: PhaseRun) => void
  onChangeModel: (run: PhaseRun) => void
}) {
  const avatar = ROLE_AVATARS[phase.role] || { icon: '🤖', color: 'from-gray-400 to-gray-600' }
  const status = run?.status || 'pending'
  const style = STATUS_STYLE[status] || STATUS_STYLE.pending
  const isRunning = status === 'running'
  const awaitingApproval = status === 'awaiting_approval'
  const tokens = (run?.input_tokens || 0) + (run?.output_tokens || 0)
  const assignedModel = run?.model_id || phase.model || phase.default_model || '—'
  const canChangeModel = !!run && (status === 'failed' || status === 'awaiting_approval' || status === 'rejected')

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
          <span className="font-mono truncate">{assignedModel}</span>
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
          <div className="space-y-2">
            <div className="text-xs font-semibold text-red-600 dark:text-red-400">Phase failed</div>
            {run?.raw_response && (
              <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-3 py-2 text-xs text-red-700 dark:text-red-200 whitespace-pre-wrap break-words">
                {run.raw_response}
              </div>
            )}
          </div>
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

        {canChangeModel && (
          <button
            onClick={() => onChangeModel(run)}
            className="mt-3 w-full px-3 py-2 text-xs font-semibold rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/60 transition-colors"
          >
            Change model for this phase
          </button>
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

function ChangeModelModal({
  run,
  phase,
  models,
  onClose,
  onSubmit,
}: {
  run: PhaseRun
  phase: PhaseDef | undefined
  models: ModelOption[]
  onClose: () => void
  onSubmit: (phaseIndex: number, modelId: string) => Promise<void>
}) {
  const currentModel = run.model_id || phase?.model || phase?.default_model || ''
  const [selectedModel, setSelectedModel] = useState(currentModel)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!selectedModel) {
      setError('Choose a validated model before continuing.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit(run.phase_index, selectedModel)
      onClose()
    } catch (e: any) {
      setError(e.message || 'Failed to change model')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
              Change model: {run.phase_name}
            </h2>
            <p className="text-xs text-gray-500 mt-1">
              Pick a validated model and re-run this phase from the same step.
            </p>
          </div>
          <button onClick={onClose} disabled={busy} className="text-gray-400 hover:text-gray-600 disabled:opacity-30">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 px-3 py-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-amber-800 dark:text-amber-200">Current phase state</div>
            <div className="text-sm text-amber-900 dark:text-amber-100 mt-1">
              {run.status.replace(/_/g, ' ')} with <span className="font-mono">{currentModel || 'no assigned model'}</span>
            </div>
            {run.raw_response && (
              <div className="mt-2 text-xs text-amber-900/90 dark:text-amber-100/90 whitespace-pre-wrap break-words">
                {run.raw_response}
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
              New model
            </label>
            <select
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              <option value="">Choose a validated model</option>
              {models.map(model => (
                <option key={model.id} value={model.model_id}>
                  {model.display_name || model.model_id}{model.provider_name ? ` (${model.provider_name})` : ''}
                </option>
              ))}
            </select>
            <div className="mt-1 text-[11px] text-gray-500">
              Only active, validated, confirmed-working models are shown here.
            </div>
          </div>

          {error && (
            <div className="text-xs text-red-600 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-800 flex gap-3 justify-end">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 text-sm font-medium rounded-lg text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={busy || !selectedModel}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40"
          >
            {busy ? 'Switching…' : 'Switch model & re-run'}
          </button>
        </div>
      </div>
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
  onApprove: (feedback?: string, phaseIndex?: number) => Promise<void>
  onReject: (feedback: string, phaseIndex?: number) => Promise<void>
  onSkip: (reason?: string, phaseIndex?: number) => Promise<void>
}) {
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState<'approve' | 'reject' | 'skip' | null>(null)

  const handleApprove = async () => {
    setBusy('approve')
    try { await onApprove(feedback || undefined, run.phase_index); onClose() } finally { setBusy(null) }
  }
  const handleReject = async () => {
    if (!feedback.trim()) { alert('Rejection requires feedback — tell the agent what to fix.'); return }
    setBusy('reject')
    try { await onReject(feedback, run.phase_index); onClose() } finally { setBusy(null) }
  }
  const handleSkip = async () => {
    setBusy('skip')
    try { await onSkip(feedback || undefined, run.phase_index); onClose() } finally { setBusy(null) }
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
  const apiBase = getApiBase()
  const authHeaders = getAuthHeaders()
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
      const res = await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/save-as-template`, {
        method: 'POST',
        headers: authHeaders,
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

// ─── Swim Lane View ───────────────────────────────────────────────────────────

/** Group phases into layers by dependency depth (topological sort level). */
function buildLayers(phases: PhaseDef[]): number[][] {
  const nameToIdx: Record<string, number> = {}
  phases.forEach((p, i) => { nameToIdx[p.name] = i })

  const depth = new Array(phases.length).fill(0)
  const visited = new Set<number>()

  function dfs(idx: number): number {
    if (visited.has(idx)) return depth[idx]
    visited.add(idx)
    const deps = phases[idx].depends_on || []
    let maxParent = -1
    for (const dep of deps) {
      if (nameToIdx[dep] !== undefined) {
        maxParent = Math.max(maxParent, dfs(nameToIdx[dep]))
      }
    }
    depth[idx] = maxParent + 1
    return depth[idx]
  }

  for (let i = 0; i < phases.length; i++) dfs(i)

  const maxDepth = Math.max(...depth, 0)
  const layers: number[][] = Array.from({ length: maxDepth + 1 }, () => [])
  depth.forEach((d, i) => layers[d].push(i))
  return layers
}

const LANE_STATUS: Record<string, { border: string; bg: string; dot: string }> = {
  pending:           { border: 'border-gray-300 dark:border-gray-600',   bg: 'bg-gray-50 dark:bg-gray-800/50',     dot: 'bg-gray-400' },
  running:           { border: 'border-blue-400 dark:border-blue-500',   bg: 'bg-blue-50 dark:bg-blue-900/20',     dot: 'bg-blue-500' },
  awaiting_approval: { border: 'border-amber-400 dark:border-amber-500', bg: 'bg-amber-50 dark:bg-amber-900/10',   dot: 'bg-amber-500' },
  approved:          { border: 'border-green-400 dark:border-green-500', bg: 'bg-green-50 dark:bg-green-900/10',   dot: 'bg-green-500' },
  rejected:          { border: 'border-red-400 dark:border-red-500',     bg: 'bg-red-50 dark:bg-red-900/10',       dot: 'bg-red-500' },
  failed:            { border: 'border-red-400 dark:border-red-500',     bg: 'bg-red-50 dark:bg-red-900/10',       dot: 'bg-red-500' },
  skipped:           { border: 'border-gray-300 dark:border-gray-600',   bg: 'bg-gray-50 dark:bg-gray-800/50',     dot: 'bg-gray-400' },
}

function formatDuration(startedAt?: string, completedAt?: string): string | null {
  if (!startedAt) return null
  const start = new Date(startedAt).getTime()
  const end = completedAt ? new Date(completedAt).getTime() : Date.now()
  const sec = Math.round((end - start) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  return `${min}m ${sec % 60}s`
}

function estimateTokenCost(input: number, output: number): string {
  // Rough estimate: $3 per 1M input, $15 per 1M output (Claude-class pricing)
  const cost = (input * 3 + output * 15) / 1_000_000
  if (cost < 0.001) return '<$0.001'
  return `$${cost.toFixed(3)}`
}

function BranchTooltip({ phase, run, children }: {
  phase: PhaseDef
  run: PhaseRun | null
  children: React.ReactNode
}) {
  const [show, setShow] = useState(false)
  const condition = phase.branch_condition
  const result = run?.branch_result
  const taken = run?.branch_taken

  if (!condition && !result && !taken) return <>{children}</>

  return (
    <div className="relative" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      {show && (
        <div className="absolute z-30 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 bg-gray-900 text-gray-100 rounded-lg shadow-xl p-3 text-xs space-y-1.5 pointer-events-none">
          <div className="font-semibold text-amber-300">Branch Decision</div>
          {condition && (
            <div><span className="text-gray-400">Condition:</span> <span className="font-mono">{condition}</span></div>
          )}
          {result && (
            <div><span className="text-gray-400">Result:</span> <span className="font-mono">{result}</span></div>
          )}
          {taken && (
            <div><span className="text-gray-400">Path taken:</span> <span className="text-green-400 font-semibold">{taken}</span></div>
          )}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[6px] border-t-gray-900" />
        </div>
      )}
    </div>
  )
}

function RetryIndicator({ count }: { count: number }) {
  return (
    <div className="absolute -top-1.5 -right-1.5 z-20 flex items-center gap-0.5 bg-amber-500 text-white rounded-full px-1.5 py-0.5 text-[9px] font-bold shadow-md" title={`Retried ${count} time${count > 1 ? 's' : ''}`}>
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 4v6h6" />
        <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
      </svg>
      {count}
    </div>
  )
}

function SwimLaneView({
  phases, runsByIndex,
}: {
  phases: PhaseDef[]
  runsByIndex: Record<number, PhaseRun>
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const [arrows, setArrows] = useState<{ x1: number; y1: number; x2: number; y2: number; inactive?: boolean }[]>([])

  const layers = buildLayers(phases)
  const nameToIdx: Record<string, number> = {}
  phases.forEach((p, i) => { nameToIdx[p.name] = i })

  // Compute SVG arrows after layout
  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      if (!containerRef.current) return
      const containerRect = containerRef.current.getBoundingClientRect()
      const newArrows: typeof arrows = []

      phases.forEach((phase, idx) => {
        const deps = phase.depends_on || []
        const targetCard = cardRefs.current[idx]
        if (!targetCard) return
        const targetRun = runsByIndex[idx]
        const targetSkipped = targetRun?.status === 'skipped'

        for (const dep of deps) {
          const srcIdx = nameToIdx[dep]
          if (srcIdx === undefined) continue
          const srcCard = cardRefs.current[srcIdx]
          if (!srcCard) continue

          const srcRect = srcCard.getBoundingClientRect()
          const tgtRect = targetCard.getBoundingClientRect()

          newArrows.push({
            x1: srcRect.left + srcRect.width / 2 - containerRect.left,
            y1: srcRect.bottom - containerRect.top,
            x2: tgtRect.left + tgtRect.width / 2 - containerRect.left,
            y2: tgtRect.top - containerRect.top,
            inactive: targetSkipped,
          })
        }
      })
      setArrows(newArrows)
    })
    return () => cancelAnimationFrame(raf)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phases, runsByIndex])

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-1">
        <span className="font-semibold uppercase tracking-wider">Pipeline Timeline</span>
        <span className="text-gray-300 dark:text-gray-600">—</span>
        <span>Sequential ↓ · Parallel ↔ · ◇ Branch</span>
      </div>
      <div ref={containerRef} className="relative overflow-x-auto">
        {/* SVG arrow overlay */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none z-10" style={{ overflow: 'visible' }}>
          <defs>
            <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <path d="M0,0 L8,3 L0,6" fill="none" stroke="currentColor" className="text-gray-400 dark:text-gray-500" strokeWidth="1.5" />
            </marker>
            <marker id="arrowhead-inactive" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <path d="M0,0 L8,3 L0,6" fill="none" stroke="currentColor" className="text-gray-300 dark:text-gray-700" strokeWidth="1.5" />
            </marker>
          </defs>
          {arrows.map((a, i) => {
            const midY = (a.y1 + a.y2) / 2
            return (
              <path
                key={i}
                d={`M${a.x1},${a.y1} C${a.x1},${midY} ${a.x2},${midY} ${a.x2},${a.y2}`}
                fill="none"
                stroke="currentColor"
                className={a.inactive ? 'text-gray-200 dark:text-gray-700' : 'text-gray-300 dark:text-gray-600'}
                strokeWidth={a.inactive ? 1.5 : 2}
                strokeDasharray={a.inactive ? '4 3' : undefined}
                markerEnd={a.inactive ? 'url(#arrowhead-inactive)' : 'url(#arrowhead)'}
              />
            )
          })}
        </svg>

        {/* Layers */}
        <div className="flex flex-col gap-6">
          {layers.map((layer, layerIdx) => (
            <div key={layerIdx} className="flex items-stretch justify-center gap-4 relative">
              {/* Layer label */}
              <div className="flex items-center justify-center w-8 flex-shrink-0">
                <span className="text-[10px] font-mono text-gray-400 dark:text-gray-500 -rotate-90 whitespace-nowrap">
                  L{layerIdx}
                </span>
              </div>
              {/* Phase cards in this layer */}
              <div className={`flex-1 grid gap-4`} style={{
                gridTemplateColumns: `repeat(${layer.length}, minmax(200px, 1fr))`
              }}>
                {layer.map(phaseIdx => {
                  const phase = phases[phaseIdx]
                  const run = runsByIndex[phaseIdx] || null
                  const status = run?.status || 'pending'
                  const style = LANE_STATUS[status] || LANE_STATUS.pending
                  const avatar = ROLE_AVATARS[phase.role] || { icon: '🤖', color: 'from-gray-400 to-gray-600' }
                  const isRunning = status === 'running'
                  const tokens = (run?.input_tokens || 0) + (run?.output_tokens || 0)
                  const duration = formatDuration(run?.started_at, run?.completed_at)
                  const isDone = status === 'approved' || status === 'skipped'
                  const isBranch = phase.phase_type === 'branch'
                  const isInactive = status === 'skipped'
                  const retryCount = run?.retry_count || 0

                  const cardContent = (
                    <div
                      key={phaseIdx}
                      ref={el => { cardRefs.current[phaseIdx] = el }}
                      className={`relative transition-all
                        ${isBranch ? 'flex items-center justify-center' : ''}
                        ${isInactive ? 'opacity-40' : ''}`}
                    >
                      {retryCount > 0 && <RetryIndicator count={retryCount} />}
                      {isBranch ? (
                        /* ◇ Diamond node for branch phases */
                        <div className={`relative w-32 h-32 flex items-center justify-center`}>
                          <div
                            className={`absolute w-24 h-24 border-2 ${style.border} ${style.bg} rotate-45 rounded-md transition-all
                              ${isRunning ? 'animate-pulse ring-2 ring-blue-400/50 dark:ring-blue-500/40' : ''}`}
                          />
                          {/* Content inside diamond (counter-rotated) */}
                          <div className="relative z-10 flex flex-col items-center gap-1 text-center px-1">
                            <div className={`w-6 h-6 rounded-full bg-gradient-to-br ${avatar.color} flex items-center justify-center text-xs flex-shrink-0`}>
                              {avatar.icon}
                            </div>
                            <div className="text-[11px] font-semibold text-gray-900 dark:text-white leading-tight max-w-[5rem] truncate">
                              {phase.name}
                            </div>
                            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${style.dot}`} />
                            {run?.branch_taken && (
                              <div className="text-[9px] text-green-600 dark:text-green-400 font-semibold truncate max-w-[5rem]">
                                → {run.branch_taken}
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        /* Standard rectangular card */
                        <div
                          className={`rounded-lg border-2 ${style.border} ${style.bg} p-3 transition-all
                            ${isRunning ? 'animate-pulse ring-2 ring-blue-400/50 dark:ring-blue-500/40' : ''}`}
                        >
                          {/* Header row */}
                          <div className="flex items-center gap-2 mb-1.5">
                            <div className={`w-7 h-7 rounded-full bg-gradient-to-br ${avatar.color} flex items-center justify-center text-sm flex-shrink-0`}>
                              {avatar.icon}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">{phase.name}</div>
                              <div className="text-[10px] text-gray-500 dark:text-gray-400 truncate">{phase.role}</div>
                            </div>
                            <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${style.dot}`} title={STATUS_STYLE[status]?.label || status} />
                          </div>
                          {/* Meta row */}
                          <div className="flex items-center gap-2 text-[10px] text-gray-500 dark:text-gray-400 flex-wrap">
                            <span className={`uppercase font-semibold tracking-wider ${STATUS_STYLE[status]?.text || 'text-gray-500'}`}>
                              {STATUS_STYLE[status]?.label || status}
                            </span>
                            {duration && <span className="font-mono">⏱ {duration}</span>}
                            {isDone && tokens > 0 && (
                              <>
                                <span className="font-mono">{tokens.toLocaleString()} tok</span>
                                <span className="font-mono">{estimateTokenCost(run?.input_tokens || 0, run?.output_tokens || 0)}</span>
                              </>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )

                  return isBranch
                    ? <BranchTooltip key={phaseIdx} phase={phase} run={run}>{cardContent}</BranchTooltip>
                    : <div key={phaseIdx}>{cardContent}</div>
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function PipelinePage() {
  const params = useParams()
  const router = useRouter()
  const pipelineId = Array.isArray(params?.id) ? params.id[0] : params?.id as string
  const apiBase = getApiBase()
  const authHeaders = getAuthHeaders()

  const [pipeline, setPipeline] = useState<Pipeline | null>(null)
  const [phaseRuns, setPhaseRuns] = useState<PhaseRun[]>([])
  const [models, setModels] = useState<ModelOption[]>([])
  const [events, setEvents] = useState<PipelineEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [approvalRun, setApprovalRun] = useState<PhaseRun | null>(null)
  const [viewArtifactRun, setViewArtifactRun] = useState<PhaseRun | null>(null)
  const [changeModelRun, setChangeModelRun] = useState<PhaseRun | null>(null)
  const [showSaveTemplate, setShowSaveTemplate] = useState(false)
  const [guidance, setGuidance] = useState('')
  const [sendingGuidance, setSendingGuidance] = useState(false)
  const [connectionState, setConnectionState] = useState<'connecting' | 'live' | 'reconnecting'>('connecting')

  // Escape closes the read-only artifact modal
  useEffect(() => {
    if (!viewArtifactRun) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') setViewArtifactRun(null) }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [viewArtifactRun])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const seenEventKeysRef = useRef<Set<string>>(new Set())

  const appendEvent = useCallback((evt: PipelineEvent) => {
    if (!evt || !evt.type || evt.type === 'ping' || evt.type === 'init') return
    const key = makeEventKey(evt)
    if (seenEventKeysRef.current.has(key)) return
    seenEventKeysRef.current.add(key)
    setEvents(curr => {
      if (evt.type === 'phase_progress' && curr.length > 0) {
        const last = curr[curr.length - 1]
        if (last.type === 'phase_progress' && last.payload?.phase_index === evt.payload?.phase_index) {
          return [...curr.slice(0, -1), evt]
        }
      }
      const next = [...curr, evt]
      return next.slice(-160)
    })
  }, [])

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
      const res = await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}`, { headers: authHeaders })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setPipeline(data)
      setPhaseRuns(data.phase_runs || [])
      setLoading(false)
      setLoadError(null)
    } catch (e: any) {
      setLoadError(e.message || 'Failed to load pipeline')
      setLoading(false)
    }
  }, [apiBase, authHeaders, pipelineId])

  const fetchModels = useCallback(async () => {
    try {
      const res = await fetch(
        `${apiBase}/v1/models?active_only=true&usable_only=true&validated_only=true`,
        { headers: authHeaders },
      )
      const payload = await readApiPayload(res)
      if (!res.ok) throw new Error(getApiErrorMessage(payload, res.status))
      setModels(Array.isArray(payload?.data) ? payload.data : [])
    } catch (e: any) {
      setActionError(e.message || 'Failed to load available models')
    }
  }, [apiBase, authHeaders])

  // Initial fetch
  useEffect(() => {
    if (!pipelineId) return
    refetch()
  }, [pipelineId, refetch])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  // SSE subscription
  useEffect(() => {
    if (!pipelineId) return
    setConnectionState('connecting')
    const es = new EventSource(`${apiBase}/v1/workbench/pipelines/${pipelineId}/stream`)
    esRef.current = es

    es.onopen = () => setConnectionState('live')

    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data)
        if (evt.type === 'ping') return
        if (evt.type === 'init') {
          setPipeline(evt.payload)
          setPhaseRuns(evt.payload.phase_runs || [])
          setLoading(false)
          return
        }
        appendEvent(evt)
        if (EVENT_REFRESH_TYPES.has(evt.type)) {
          refetch()
        }
      } catch {}
    }
    es.onerror = () => { setConnectionState('reconnecting') }

    return () => { es.close(); esRef.current = null }
  }, [apiBase, appendEvent, pipelineId, refetch])

  const approve = async (feedback?: string, phaseIndex?: number) => {
    const qs = phaseIndex !== undefined ? `?phase_index=${phaseIndex}` : ''
    await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/approve${qs}`, {
      method: 'POST', headers: authHeaders,
      body: JSON.stringify({ feedback: feedback || null }),
    })
    refetch()
  }
  const reject = async (feedback: string, phaseIndex?: number) => {
    const qs = phaseIndex !== undefined ? `?phase_index=${phaseIndex}` : ''
    await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/reject${qs}`, {
      method: 'POST', headers: authHeaders,
      body: JSON.stringify({ feedback }),
    })
    refetch()
  }
  const skip = async (reason?: string, phaseIndex?: number) => {
    const qs = phaseIndex !== undefined ? `?phase_index=${phaseIndex}` : ''
    await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/skip${qs}`, {
      method: 'POST', headers: authHeaders,
      body: JSON.stringify({ reason: reason || null }),
    })
    refetch()
  }
  const cancelPipeline = async () => {
    if (!confirm('Cancel this pipeline? Any running phase will be abandoned.')) return
    await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/cancel`, {
      method: 'POST', headers: authHeaders,
    })
    refetch()
  }
  const pausePipeline = async () => {
    await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/pause`, {
      method: 'POST', headers: authHeaders,
    })
    refetch()
  }
  const resumePipeline = async () => {
    await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/resume`, {
      method: 'POST', headers: authHeaders,
    })
    refetch()
  }
  const retryPipeline = async () => {
    await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/retry`, {
      method: 'POST', headers: authHeaders,
    })
    refetch()
  }
  const changePhaseModel = useCallback(async (phaseIndex: number, modelId: string) => {
    setActionError(null)
    const res = await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/phase-model`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({ phase_index: phaseIndex, model_id: modelId }),
    })
    const payload = await readApiPayload(res)
    if (!res.ok) {
      throw new Error(getApiErrorMessage(payload, res.status))
    }
    await refetch()
  }, [apiBase, authHeaders, pipelineId, refetch])
  const sendGuidance = useCallback(async () => {
    const message = guidance.trim()
    if (!message) return
    setSendingGuidance(true)
    setActionError(null)
    try {
      const res = await fetch(`${apiBase}/v1/workbench/pipelines/${pipelineId}/message`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ message }),
      })
      const payload = await readApiPayload(res)
      if (!res.ok) {
        throw new Error(getApiErrorMessage(payload, res.status))
      }
      setGuidance('')
    } catch (e: any) {
      setActionError(e.message || 'Failed to send guidance')
    } finally {
      setSendingGuidance(false)
    }
  }, [apiBase, authHeaders, guidance, pipelineId])

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="flex gap-1.5">{[0,1,2].map(i =>
          <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}
        </div>
      </div>
    )
  }

  if (!pipeline) {
    return (
      <div className="text-center py-20">
        <div className="text-5xl mb-4">⚠️</div>
        <h3 className="text-lg font-semibold mb-2">Could not load pipeline</h3>
        <p className="text-sm text-gray-500 mb-4">{loadError || 'Pipeline not found'}</p>
        <button onClick={() => router.push('/workbench')} className="text-sm text-indigo-600 hover:underline">
          ← Back to workbench
        </button>
      </div>
    )
  }

  const statusBadge = STATUS_STYLE[pipeline.status] || STATUS_STYLE.pending
  const totalTokens = phaseRuns.reduce((sum, r) => sum + (r.input_tokens || 0) + (r.output_tokens || 0), 0)
  const currentPhaseRun = runsByIndex[pipeline.current_phase_index]
  const connectionLabel = connectionState === 'live' ? 'Live' : connectionState === 'reconnecting' ? 'Reconnecting…' : 'Connecting…'
  const connectionClasses = connectionState === 'live'
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
    : connectionState === 'reconnecting'
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
      : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'

  // Parallel approval: all phases currently awaiting approval
  const awaitingRuns = Object.values(runsByIndex).filter(r => r.status === 'awaiting_approval')
  // Progress: count phases with terminal status
  const completedCount = Object.values(runsByIndex).filter(r =>
    r.status === 'approved' || r.status === 'skipped'
  ).length
  const totalPhases = pipeline.phases.length
  const latestEvent = [...events].reverse().find(evt => evt.type !== 'phase_progress') || null
  const latestAlert = [...events].reverse().find(evt =>
    evt.type === 'phase_failed' || evt.type === 'warning' || evt.type === 'awaiting_approval' || evt.type === 'pipeline_done'
  ) || null
  const latestEventSummary = latestEvent ? describeEvent(latestEvent, pipeline.phases) : null
  const latestAlertSummary = latestAlert ? describeEvent(latestAlert, pipeline.phases) : null

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
            <span className={`text-xs font-semibold px-2 py-0.5 rounded ${connectionClasses}`}>
              {connectionLabel}
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
          {latestEventSummary && (
            <div className="mt-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 dark:text-gray-400">Latest update</div>
              <div className="text-sm font-medium text-gray-900 dark:text-white mt-1">{latestEventSummary.title}</div>
              {latestEventSummary.detail && (
                <div className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">{latestEventSummary.detail}</div>
              )}
            </div>
          )}
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
          {pipeline.status === 'running' && (
            <button onClick={pausePipeline}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800/60">
              Pause
            </button>
          )}
          {pipeline.status === 'paused' && (
            <button onClick={resumePipeline}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-700 hover:bg-slate-800 text-white">
              Resume
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

      <div className="rounded-2xl border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/20 px-4 py-3">
        <div className="text-sm font-semibold text-indigo-900 dark:text-indigo-200">How to use this pipeline view</div>
        <div className="mt-1 text-sm text-indigo-800 dark:text-indigo-100">
          This is now a supervisor workspace rather than a plain chat thread. Watch the live activity feed, send guidance that carries into the next phase or retry, and review artifacts before approving the handoff.
        </div>
      </div>

      {loadError && (
        <div className="rounded-2xl border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/20 px-4 py-3">
          <div className="text-sm font-semibold text-amber-900 dark:text-amber-200">Refresh warning</div>
          <div className="text-sm text-amber-800 dark:text-amber-100 mt-1">{loadError}</div>
        </div>
      )}

      {latestAlertSummary && (
        <div className={`rounded-2xl border px-4 py-3 ${
          latestAlert?.type === 'phase_failed' || (latestAlert?.type === 'pipeline_done' && pipeline.status !== 'completed')
            ? 'border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-900/20'
            : latestAlert?.type === 'awaiting_approval'
              ? 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/20'
              : 'border-yellow-300 bg-yellow-50 dark:border-yellow-700 dark:bg-yellow-900/20'
        }`}>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">{latestAlertSummary.title}</div>
          {latestAlertSummary.detail && (
            <div className="text-sm text-gray-700 dark:text-gray-300 mt-1">{latestAlertSummary.detail}</div>
          )}
        </div>
      )}

      {/* Progress indicator */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
          <span className="font-semibold">{completedCount} of {totalPhases} phases complete</span>
          <span>{Math.round((completedCount / totalPhases) * 100)}%</span>
        </div>
        <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-green-400 to-emerald-500 rounded-full transition-all duration-500"
            style={{ width: `${(completedCount / totalPhases) * 100}%` }}
          />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          {/* Awaiting-approval banner — shows ALL phases needing review */}
          {awaitingRuns.length > 0 && (
            <div className="rounded-xl border-2 border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 p-4 space-y-3">
              <div className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                {awaitingRuns.length === 1
                  ? '1 phase awaiting your review'
                  : `${awaitingRuns.length} phases awaiting your review`}
              </div>
              <div className="space-y-2">
                {awaitingRuns.map(run => (
                  <div key={run.id} className="flex items-center justify-between gap-3 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-amber-200 dark:border-amber-800">
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-gray-900 dark:text-white">{run.phase_name}</span>
                      <span className="text-xs text-gray-500 ml-2">({run.agent_role})</span>
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                      <button
                        onClick={() => { skip(undefined, run.phase_index) }}
                        className="px-2.5 py-1 text-xs font-medium rounded-md text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600">
                        ⏭ Skip
                      </button>
                      <button
                        onClick={() => setApprovalRun(run)}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-amber-500 hover:bg-amber-600 text-white">
                        👁 Review
                      </button>
                      <button
                        onClick={() => { approve(undefined, run.phase_index) }}
                        className="px-2.5 py-1 text-xs font-medium rounded-md bg-green-600 hover:bg-green-700 text-white">
                        ✓ Approve
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Swim-lane timeline (parallel phases side-by-side) */}
          <SwimLaneView phases={pipeline.phases} runsByIndex={runsByIndex} />

          {/* Detailed phase cards */}
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">Phase Details</div>
            <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${Math.min(pipeline.phases.length, 3)}, minmax(240px, 1fr))` }}>
              {pipeline.phases.map((phase, idx) => (
                <PhaseCard
                  key={idx}
                  phase={phase}
                  run={runsByIndex[idx] || null}
                  isCurrent={idx === pipeline.current_phase_index && pipeline.status !== 'completed'}
                  onOpenApproval={setApprovalRun}
                  onViewArtifact={setViewArtifactRun}
                  onChangeModel={setChangeModelRun}
                />
              ))}
            </div>
          </div>
        </div>

        <aside className="space-y-4 xl:sticky xl:top-4 self-start">
          <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-3">
            <div>
              <div className="text-sm font-semibold text-gray-900 dark:text-white">Send guidance</div>
              <div className="text-xs text-gray-500 mt-1">Guidance is recorded immediately and carried into the next phase or retry.</div>
            </div>
            <textarea
              value={guidance}
              onChange={e => setGuidance(e.target.value)}
              onKeyDown={e => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                  e.preventDefault()
                  sendGuidance()
                }
              }}
              rows={4}
              placeholder="Tell the pipeline what to prioritize, avoid, or verify next…"
              className="w-full rounded-xl border border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <button
              onClick={sendGuidance}
              disabled={!guidance.trim() || sendingGuidance}
              className="w-full rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 disabled:opacity-50"
            >
              {sendingGuidance ? 'Sending…' : 'Send guidance'}
            </button>
            {actionError && (
              <div className="text-[11px] text-red-600 dark:text-red-300">{actionError}</div>
            )}
            {currentPhaseRun?.status === 'running' && (
              <div className="text-[11px] text-amber-600 dark:text-amber-300">
                The current phase keeps running. Your note will be applied when the pipeline reaches its next handoff or retry.
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-gray-900 dark:text-white">Live activity</div>
                  <div className="text-xs text-gray-500 mt-1">Continuous status, failures, and handoffs.</div>
                </div>
                <span className={`text-[11px] font-semibold px-2 py-1 rounded-full ${connectionClasses}`}>
                  {connectionLabel}
                </span>
              </div>
            </div>
            <div className="max-h-[34rem] overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800">
              {events.length === 0 ? (
                <div className="px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
                  Waiting for live pipeline events. As phases start, stream, fail, or request approval, they will appear here.
                </div>
              ) : (
                [...events].reverse().map((evt, idx) => {
                  const summary = describeEvent(evt, pipeline.phases)
                  const toneClasses = summary.tone === 'error'
                    ? 'border-red-200 bg-red-50 dark:border-red-900/40 dark:bg-red-900/10'
                    : summary.tone === 'warning'
                      ? 'border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-900/10'
                      : summary.tone === 'success'
                        ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-900/40 dark:bg-emerald-900/10'
                        : 'border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900'
                  return (
                    <div key={`${makeEventKey(evt)}-${idx}`} className={`px-4 py-3 border-l-2 ${toneClasses}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 dark:text-white">{summary.title}</div>
                          {summary.detail && (
                            <div className="text-xs text-gray-600 dark:text-gray-300 mt-1 whitespace-pre-wrap break-words">{summary.detail}</div>
                          )}
                        </div>
                        <div className="text-[11px] text-gray-400 whitespace-nowrap">{formatEventTime(evt.ts)}</div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </aside>
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

      {changeModelRun && (
        <ChangeModelModal
          run={changeModelRun}
          phase={pipeline.phases[changeModelRun.phase_index]}
          models={models}
          onClose={() => setChangeModelRun(null)}
          onSubmit={changePhaseModel}
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
