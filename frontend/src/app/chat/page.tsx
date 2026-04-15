'use client'

import { API_BASE, API_KEY, AUTH_HEADERS } from '@/lib/config'
import VoiceMode, { VoiceModeToggle } from '@/components/VoiceMode'

import { useState, useEffect, useRef, useCallback, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useToast } from '../ToastProvider'

// ─── Constants ────────────────────────────────────────────────────────────────

// ─── Types ────────────────────────────────────────────────────────────────────
interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  model?: string
  created_at: string
  streaming?: boolean
  image_url?: string   // inline generated image
  image_meta?: {       // generation metadata for display
    provider: string
    workflow: string
    checkpoint: string
  }
}

interface Conversation {
  id: string
  title: string | null
  pinned: boolean
  keep_forever: boolean
  last_message_at: string | null
  message_count: number
  created_at: string
  persona_id: string | null
}

interface Model {
  id: string
  model_id: string
  display_name: string
  is_active: boolean
  provider_name?: string
}

interface Persona {
  id: string
  name: string
  description?: string
  is_default?: boolean
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d}d ago`
  return new Date(dateStr).toLocaleDateString()
}

function groupByDay(convs: Conversation[]): Record<string, Conversation[]> {
  const now = new Date()
  const today = now.toDateString()
  const yesterday = new Date(now.getTime() - 86400000).toDateString()
  const weekAgo = now.getTime() - 7 * 86400000
  const groups: Record<string, Conversation[]> = {
    Pinned: [],
    Today: [],
    Yesterday: [],
    'Last 7 days': [],
    Older: [],
  }

  // Sort by most recent first before grouping
  const sorted = [...convs].sort((a, b) => {
    const ta = new Date(a.last_message_at || a.created_at).getTime()
    const tb = new Date(b.last_message_at || b.created_at).getTime()
    return tb - ta
  })

  for (const c of sorted) {
    if (c.pinned) { groups['Pinned'].push(c); continue }
    const d = new Date(c.last_message_at || c.created_at)
    if (d.toDateString() === today) groups['Today'].push(c)
    else if (d.toDateString() === yesterday) groups['Yesterday'].push(c)
    else if (d.getTime() > weekAgo) groups['Last 7 days'].push(c)
    else groups['Older'].push(c)
  }
  return groups
}

// Simple markdown renderer (no external lib)
function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Code blocks
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre class="bg-gray-100 dark:bg-gray-900 rounded-lg p-3 my-2 overflow-x-auto text-sm font-mono"><code>${code.trim()}</code></pre>`)
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-4 mb-1">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-4 mb-2">$1</h1>')
    // Bullet lists
    .replace(/^[*\-] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/(<li.*<\/li>\n?)+/g, s => `<ul class="my-2 space-y-0.5">${s}</ul>`)
    // Numbered lists
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    // Line breaks
    .replace(/\n\n/g, '</p><p class="mb-2">')
    .replace(/\n/g, '<br/>')
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────
function Sidebar({
  conversations, activeId, onSelect, onNew, onDelete, onPin, onKeepForever, onRename,
  personas, selectedPersonaId, onPersonaChange, models, selectedModelId, onModelChange,
  searchQuery, onSearchChange, collapsed, onToggle, width, onWidthChange
}: {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onPin: (id: string, val: boolean) => void
  onKeepForever: (id: string, val: boolean) => void
  onRename: (id: string, title: string) => void
  personas: Persona[]
  selectedPersonaId: string
  onPersonaChange: (id: string) => void
  models: Model[]
  selectedModelId: string
  onModelChange: (id: string) => void
  searchQuery: string
  onSearchChange: (q: string) => void
  collapsed: boolean
  onToggle: () => void
  width: number
  onWidthChange: (w: number) => void
}) {
  const [dragging, setDragging] = useState(false)

  // Drag-to-resize handler
  useEffect(() => {
    if (!dragging) return
    const onMove = (e: MouseEvent) => {
      // Clamp between 240px (min usable) and 560px (reasonable max)
      const w = Math.max(240, Math.min(560, e.clientX))
      onWidthChange(w)
    }
    const onUp = () => setDragging(false)
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [dragging, onWidthChange])
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(null)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const groups = groupByDay(conversations)

  return (
    <>
      {/* Mobile overlay */}
      {!collapsed && (
        <div className="fixed inset-0 bg-black/40 z-20 lg:hidden" onClick={onToggle} />
      )}

      {/* Sidebar panel */}
      <aside
        className={`
          fixed lg:relative inset-y-0 left-0 z-30 lg:z-auto
          flex flex-col bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700
          ${dragging ? '' : 'transition-all duration-200 ease-in-out'}
          ${collapsed ? '-translate-x-full lg:translate-x-0 lg:w-0 lg:overflow-hidden lg:border-0' : 'translate-x-0'}
        `}
        style={collapsed ? undefined : { width: `${width}px` }}
      >
        {/* Logo + collapse btn */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <Link href="/" className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
            <span className="text-orange-500">⚡</span> DevForgeAI
          </Link>
          <button onClick={onToggle} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
            </svg>
          </button>
        </div>

        {/* Back to Dashboard + New chat */}
        <div className="px-3 py-3 space-y-2">
          <Link href="/"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Dashboard
          </Link>
          <button
            onClick={onNew}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Chat
          </button>
        </div>

        {/* Persona + Model selectors */}
        <div className="px-3 pb-2 space-y-2">
          <select
            value={selectedPersonaId}
            onChange={e => onPersonaChange(e.target.value)}
            className="w-full text-xs rounded-md border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 py-1.5 pl-2 pr-6 focus:ring-orange-500 focus:border-orange-400"
          >
            {personas.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        
          {/* Model override */}
          {models.length > 0 && (
            <select
              value={selectedModelId}
              onChange={e => onModelChange(e.target.value)}
              className="w-full text-xs rounded-md border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 py-1.5 pl-2 pr-6 focus:ring-orange-500 focus:border-orange-400"
              title="Override model (overrides persona default)"
            >
              <option value="">Model: persona default</option>
              {Object.entries(
                models.reduce((acc: Record<string, Model[]>, m) => {
                  const g = m.provider_name || 'Other'
                  ;(acc[g] = acc[g] || []).push(m)
                  return acc
                }, {})
              ).map(([group, ms]) => (
                <optgroup key={group} label={group}>
                  {(ms as Model[]).map(m => (
                    <option key={m.id} value={m.model_id}>{m.display_name || m.model_id}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          )}
</div>

        {/* Search */}
        <div className="px-3 pb-2">
          <div className="relative">
            <svg className="absolute left-2.5 top-2 w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              value={searchQuery}
              onChange={e => onSearchChange(e.target.value)}
              placeholder="Search sessions…"
              className="w-full pl-7 pr-2 py-1.5 text-xs rounded-md border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 focus:ring-orange-500 focus:border-orange-400"
            />
          </div>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-4">
          {Object.entries(groups).map(([label, items]) => {
            if (items.length === 0) return null
            return (
              <div key={label}>
                <p className="px-2 py-1 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                  {label}
                </p>
                <div className="space-y-0.5">
                  {items.map(conv => (
                    <div key={conv.id} className="relative group" ref={menuOpen === conv.id ? menuRef : null}>
                      {renaming === conv.id ? (
                        <form onSubmit={e => { e.preventDefault(); onRename(conv.id, renameValue); setRenaming(null) }}
                          className="flex items-center gap-1 px-2 py-1">
                          <input
                            autoFocus
                            value={renameValue}
                            onChange={e => setRenameValue(e.target.value)}
                            onBlur={() => setRenaming(null)}
                            className="flex-1 text-xs rounded border border-orange-400 px-1.5 py-0.5 dark:bg-gray-800 dark:text-white"
                          />
                        </form>
                      ) : (
                        <button
                          onClick={() => onSelect(conv.id)}
                          className={`w-full text-left flex items-start gap-2 px-2 py-2 rounded-md text-sm transition-colors ${
                            activeId === conv.id
                              ? 'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300'
                              : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                          }`}
                        >
                          {conv.pinned && <span className="text-orange-400 mt-0.5 flex-shrink-0">📌</span>}
                          <span className="flex-1 min-w-0">
                            <span className="block truncate text-sm">
                              {conv.title || 'New conversation'}
                            </span>
                            <span className="block text-xs text-gray-400 dark:text-gray-500">
                              {timeAgo(conv.last_message_at || conv.created_at)}
                              {conv.message_count > 0 && ` · ${conv.message_count} msgs`}
                            </span>
                          </span>
                          <button
                            onClick={e => { e.stopPropagation(); setMenuOpen(menuOpen === conv.id ? null : conv.id) }}
                            className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 flex-shrink-0 mt-0.5"
                          >
                            <svg className="w-3.5 h-3.5 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                              <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                            </svg>
                          </button>
                        </button>
                      )}

                      {/* Context menu */}
                      {menuOpen === conv.id && (
                        <div className="absolute right-0 top-8 z-50 w-44 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 text-sm">
                          <button onClick={() => { setRenameValue(conv.title || ''); setRenaming(conv.id); setMenuOpen(null) }}
                            className="w-full text-left px-3 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">
                            ✏️ Rename
                          </button>
                          <button onClick={() => { onPin(conv.id, !conv.pinned); setMenuOpen(null) }}
                            className="w-full text-left px-3 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">
                            {conv.pinned ? '📌 Unpin' : '📌 Pin'}
                          </button>
                          <button onClick={() => { onKeepForever(conv.id, !conv.keep_forever); setMenuOpen(null) }}
                            className="w-full text-left px-3 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300">
                            {conv.keep_forever ? '🗓 Auto-expire' : '♾️ Keep forever'}
                          </button>
                          <hr className="my-1 border-gray-100 dark:border-gray-700" />
                          <button onClick={() => { if (confirm('Delete this conversation?')) { onDelete(conv.id); setMenuOpen(null) } }}
                            className="w-full text-left px-3 py-1.5 hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600">
                            🗑 Delete
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
          {conversations.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-8">No conversations yet</p>
          )}
        </div>

        {/* Drag handle — only visible on lg+ screens when sidebar expanded */}
        {!collapsed && (
          <div
            onMouseDown={() => setDragging(true)}
            onDoubleClick={() => onWidthChange(288)}
            title="Drag to resize • Double-click to reset"
            className={`hidden lg:block absolute top-0 right-0 w-1 h-full cursor-col-resize group ${
              dragging ? 'bg-orange-400' : 'hover:bg-orange-400/50 active:bg-orange-400'
            } transition-colors`}
          >
            <div className="absolute top-1/2 right-0 -translate-y-1/2 w-1 h-12 bg-gray-300 dark:bg-gray-600 rounded-l opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        )}
      </aside>
    </>
  )
}

// ─── Inline image with lightbox ──────────────────────────────────────────────
function InlineImage({ src, meta }: { src: string; meta?: Message['image_meta'] }) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading')
  const [lightbox, setLightbox] = useState(false)
  const [retryCount, setRetryCount] = useState(0)

  // Always construct URL fresh from current window context — handles hostname changes,
  // remote access, and stale stored URLs.
  // Extract the image path: "/v1/img/{uuid}" from any URL format
  const extractPath = (url: string) => {
    const match = url.match(/\/v1\/img\/[a-f0-9-]+/i)
    return match ? match[0] : url.startsWith('/') ? url : `/${url}`
  }
  const imgPath = extractPath(src)
  const imgSrc = `${API_BASE}${imgPath}`

  // Force a new request on retry by appending a cache-buster
  const finalSrc = retryCount > 0 ? `${imgSrc}${imgSrc.includes('?') ? '&' : '?'}r=${retryCount}` : imgSrc

  return (
    <>
      <div className="mt-2 space-y-1.5">
        {/* Image with loading/error states */}
        <div className="relative inline-block">
          {status === 'loading' && (
            <div className="flex items-center gap-2 px-4 py-6 rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 w-64">
              <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-gray-500">Loading image…</span>
            </div>
          )}
          {status === 'error' && (
            <div className="flex flex-col items-center gap-2 px-4 py-6 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 w-72">
              <span className="text-sm text-red-500">Failed to load image</span>
              <span className="text-[10px] text-gray-400 break-all text-center px-2">{imgSrc}</span>
              <button
                onClick={() => { setRetryCount(c => c + 1); setStatus('loading') }}
                className="text-xs px-3 py-1 rounded-lg bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
              >
                Retry
              </button>
              <a href={imgSrc} target="_blank" rel="noreferrer" className="text-xs text-gray-400 hover:underline">
                Open direct link ↗
              </a>
            </div>
          )}
          <img
            key={finalSrc}
            src={finalSrc}
            alt="Generated image"
            className={`rounded-xl max-w-sm w-full cursor-zoom-in hover:opacity-90 transition-opacity border border-gray-200 dark:border-gray-700 shadow-sm ${
              status !== 'loaded' ? 'hidden' : ''
            }`}
            onLoad={() => setStatus('loaded')}
            onError={() => setStatus('error')}
            onClick={() => setLightbox(true)}
          />
        </div>

        {/* Metadata badges */}
        {status === 'loaded' && meta && (
          <div className="flex flex-wrap gap-1.5 px-0.5">
            <span className="text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 px-1.5 py-0.5 rounded">
              {meta.provider}
            </span>
            {meta.checkpoint && (
              <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 px-1.5 py-0.5 rounded truncate max-w-[180px]" title={meta.checkpoint}>
                {meta.checkpoint}
              </span>
            )}
            {meta.workflow && (
              <span className="text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-500 dark:text-blue-400 px-1.5 py-0.5 rounded">
                {meta.workflow}
              </span>
            )}
          </div>
        )}

        {/* Action links */}
        {status === 'loaded' && (
          <div className="flex gap-3 px-0.5">
            <a
              href={imgSrc}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-indigo-500 hover:text-indigo-700 dark:text-indigo-400 hover:underline"
            >
              ↓ Download ↗
            </a>
            <button onClick={() => setLightbox(true)} className="text-xs text-gray-400 hover:text-gray-600 hover:underline">
              View full size ↗
            </button>
          </div>
        )}
      </div>

      {/* Lightbox modal */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setLightbox(false)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <img
              src={imgSrc}
              alt="Generated image — full size"
              className="max-w-full max-h-[85vh] rounded-lg shadow-2xl object-contain"
            />
            <div className="absolute top-3 right-3 flex gap-2">
              <a
                href={imgSrc}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 rounded-lg bg-white/90 dark:bg-gray-800/90 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-white dark:hover:bg-gray-700 shadow transition-colors"
                onClick={e => e.stopPropagation()}
              >
                ↓ Download ↗
              </a>
              <button
                onClick={() => setLightbox(false)}
                className="px-3 py-1.5 rounded-lg bg-white/90 dark:bg-gray-800/90 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-white dark:hover:bg-gray-700 shadow transition-colors"
              >
                ✕ Close
              </button>
            </div>
            {meta && (
              <div className="absolute bottom-3 left-3 flex flex-wrap gap-1.5">
                <span className="text-xs bg-white/80 dark:bg-gray-800/80 backdrop-blur px-2 py-1 rounded shadow">
                  {meta.provider}
                </span>
                {meta.checkpoint && (
                  <span className="text-xs bg-white/80 dark:bg-gray-800/80 backdrop-blur px-2 py-1 rounded shadow truncate max-w-[200px]">
                    {meta.checkpoint}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}

// ─── TTS Speaker Button ──────────────────────────────────────────────────────
const TTS_VOICES = [
  { id: 'alloy', name: 'Alloy' },
  { id: 'echo', name: 'Echo' },
  { id: 'nova', name: 'Nova' },
] as const

function SpeakerButton({ text }: { text: string }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'playing' | 'paused'>('idle')
  const [voice, setVoice] = useState('alloy')
  const [showVoiceMenu, setShowVoiceMenu] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const blobUrlRef = useRef<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close voice menu on outside click
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowVoiceMenu(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [])

  const handlePlay = async () => {
    if (status === 'playing') {
      audioRef.current?.pause()
      setStatus('paused')
      return
    }

    if (status === 'paused' && audioRef.current) {
      audioRef.current.play()
      setStatus('playing')
      return
    }

    // Stop any previous playback
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }

    setStatus('loading')
    try {
      const resp = await fetch(`${API_BASE}/v1/audio/synthesize`, {
        method: 'POST',
        headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 4096), voice }),
      })
      if (!resp.ok) {
        setStatus('idle')
        return
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      blobUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio

      audio.onended = () => {
        setStatus('idle')
        if (blobUrlRef.current) {
          URL.revokeObjectURL(blobUrlRef.current)
          blobUrlRef.current = null
        }
      }
      audio.onerror = () => {
        setStatus('idle')
        if (blobUrlRef.current) {
          URL.revokeObjectURL(blobUrlRef.current)
          blobUrlRef.current = null
        }
      }

      await audio.play()
      setStatus('playing')
    } catch {
      setStatus('idle')
    }
  }

  const handleStop = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current = null
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
    setStatus('idle')
  }

  return (
    <span className="inline-flex items-center gap-0.5 relative" ref={menuRef}>
      {/* Main play/pause/stop button */}
      <button
        onClick={handlePlay}
        disabled={status === 'loading'}
        className={`text-xs transition-opacity ${
          status === 'idle'
            ? 'opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-600'
            : status === 'loading'
            ? 'opacity-100 text-gray-400'
            : 'opacity-100 text-orange-500 hover:text-orange-600'
        }`}
        title={status === 'playing' ? 'Pause' : status === 'paused' ? 'Resume' : 'Listen'}
      >
        {status === 'loading' ? (
          <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : status === 'playing' ? (
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
        ) : status === 'paused' ? (
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M8 5v14l11-7z" />
          </svg>
        ) : (
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072M17.95 6.05a8 8 0 010 11.9M11 5L6 9H2v6h4l5 4V5z" />
          </svg>
        )}
      </button>

      {/* Stop button (visible during playing/paused) */}
      {(status === 'playing' || status === 'paused') && (
        <button
          onClick={handleStop}
          className="text-xs text-gray-400 hover:text-red-500 transition-colors"
          title="Stop"
        >
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="6" width="12" height="12" rx="1" />
          </svg>
        </button>
      )}

      {/* Voice selector toggle */}
      <button
        onClick={() => setShowVoiceMenu(!showVoiceMenu)}
        className={`text-xs transition-opacity ${
          status === 'idle'
            ? 'opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-600'
            : 'opacity-100 text-gray-400 hover:text-gray-600'
        }`}
        title="Change voice"
      >
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Voice dropdown */}
      {showVoiceMenu && (
        <div className="absolute bottom-full left-0 mb-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg py-1 z-10 min-w-[100px]">
          {TTS_VOICES.map(v => (
            <button
              key={v.id}
              onClick={() => { setVoice(v.id); setShowVoiceMenu(false) }}
              className={`block w-full text-left px-3 py-1 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 ${
                voice === v.id ? 'text-orange-500 font-medium' : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              {v.name}
            </button>
          ))}
        </div>
      )}
    </span>
  )
}

// ─── Message bubble ───────────────────────────────────────────────────────────
function MessageBubble({ msg, conversationId }: { msg: Message; conversationId?: string | null }) {
  const [copied, setCopied] = useState(false)
  const [feedbackRating, setFeedbackRating] = useState<number | null>(null)
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [showFeedbackInput, setShowFeedbackInput] = useState(false)
  const [feedbackText, setFeedbackText] = useState('')
  const [feedbackSending, setFeedbackSending] = useState(false)
  const isUser = msg.role === 'user'

  const copy = () => {
    navigator.clipboard.writeText(msg.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const submitFeedback = async (rating: number, text?: string) => {
    if (feedbackSent || feedbackSending) return
    setFeedbackSending(true)
    try {
      await fetch(`${API_BASE}/v1/feedback`, {
        method: 'POST',
        headers: { ...AUTH_HEADERS },
        body: JSON.stringify({
          message_id: msg.id,
          conversation_id: conversationId || null,
          model_id: msg.model || null,
          rating,
          feedback_text: text || null,
        }),
      })
      setFeedbackRating(rating)
      setFeedbackSent(true)
      setShowFeedbackInput(false)
    } catch {
      // silently fail — feedback is non-critical
    } finally {
      setFeedbackSending(false)
    }
  }

  const handleThumbsUp = () => {
    if (feedbackSent) return
    submitFeedback(5)
  }

  const handleThumbsDown = () => {
    if (feedbackSent) return
    setShowFeedbackInput(true)
  }

  const handleFeedbackSubmit = () => {
    submitFeedback(1, feedbackText.trim() || undefined)
  }

  const handleFeedbackKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleFeedbackSubmit()
    }
    if (e.key === 'Escape') {
      setShowFeedbackInput(false)
      setFeedbackText('')
    }
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'} group`}>
      {/* Avatar */}
      <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-1 ${
        isUser ? 'bg-indigo-500 text-white' : 'bg-orange-100 dark:bg-orange-900 text-orange-600 dark:text-orange-300'
      }`}>
        {isUser ? 'U' : '⚡'}
      </div>

      {/* Bubble */}
      <div className={`relative max-w-[75%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
        <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'bg-indigo-600 text-white rounded-tr-sm'
            : 'bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-tl-sm shadow-sm'
        }`}>
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{msg.content}</p>
          ) : (
            msg.streaming ? (
              <p className="whitespace-pre-wrap break-words">{msg.content}<span className="inline-block w-1.5 h-4 bg-current opacity-70 animate-pulse ml-0.5 align-text-bottom" /></p>
            ) : (
              <div
                className="prose prose-sm dark:prose-invert max-w-none break-words"
                dangerouslySetInnerHTML={{ __html: `<p class="mb-2">${renderMarkdown(msg.content)}</p>` }}
              />
            )
          )}
        </div>

        {/* Inline generated image */}
        {msg.image_url && (
          <InlineImage src={msg.image_url} meta={msg.image_meta} />
        )}

        {/* Meta row */}
        <div className={`flex items-center gap-2 px-1 ${isUser ? 'flex-row-reverse' : ''}`}>
          <span className="text-xs text-gray-400">
            {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
          {msg.model && !isUser && (
            <span className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">{msg.model}</span>
          )}
          <button
            onClick={copy}
            className="opacity-0 group-hover:opacity-100 text-xs text-gray-400 hover:text-gray-600 transition-opacity"
          >
            {copied ? '✓ copied' : 'copy'}
          </button>

          {/* Feedback buttons — assistant messages only, not while streaming */}
          {!isUser && !msg.streaming && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={handleThumbsUp}
                disabled={feedbackSent}
                title="Good response"
                className={`p-0.5 rounded text-sm transition-colors ${
                  feedbackRating === 5
                    ? 'text-green-500 opacity-100'
                    : feedbackSent
                      ? 'text-gray-300 dark:text-gray-600 cursor-default'
                      : 'text-gray-400 hover:text-green-500 cursor-pointer'
                }`}
              >
                {feedbackRating === 5 ? '\u{1F44D}' : '\u{1F44D}'}
              </button>
              <button
                onClick={handleThumbsDown}
                disabled={feedbackSent}
                title="Bad response"
                className={`p-0.5 rounded text-sm transition-colors ${
                  feedbackRating === 1
                    ? 'text-red-500 opacity-100'
                    : feedbackSent
                      ? 'text-gray-300 dark:text-gray-600 cursor-default'
                      : 'text-gray-400 hover:text-red-500 cursor-pointer'
                }`}
              >
                {feedbackRating === 1 ? '\u{1F44E}' : '\u{1F44E}'}
              </button>
              {feedbackSent && (
                <span className="text-xs text-gray-400 ml-1">Thanks!</span>
              )}
            </div>
          )}
          {/* TTS listen button — assistant messages only, not while streaming */}
          {!isUser && !msg.streaming && msg.content && (
            <SpeakerButton text={msg.content} />
          )}
        </div>

        {/* Feedback text input (shown on thumbs down) */}
        {showFeedbackInput && !feedbackSent && (
          <div className="flex items-center gap-2 mt-1 w-full">
            <input
              type="text"
              value={feedbackText}
              onChange={e => setFeedbackText(e.target.value)}
              onKeyDown={handleFeedbackKeyDown}
              placeholder="What went wrong? (optional, Enter to submit)"
              autoFocus
              className="flex-1 text-xs px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            />
            <button
              onClick={handleFeedbackSubmit}
              disabled={feedbackSending}
              className="text-xs px-2 py-1.5 rounded-lg bg-red-500 text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
            >
              {feedbackSending ? '...' : 'Send'}
            </button>
            <button
              onClick={() => { setShowFeedbackInput(false); setFeedbackText('') }}
              className="text-xs px-1.5 py-1.5 text-gray-400 hover:text-gray-600"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Identity Wizard ──────────────────────────────────────────────────────────
// Handles three modes:
//   'firstrun'  — full first-run setup (soul + user + identity, 8 questions)
//   'soul'      — re-configure AI soul/personality only
//   'user'      — re-configure user profile only
//   'identity'  — re-configure AI identity/name only

export type WizardMode = 'firstrun' | 'soul' | 'user' | 'identity'

interface WizardMsg { role: 'ai' | 'user'; content: string }

interface WizardStep {
  key: string
  question: (answers: Record<string, string>) => string
  placeholder: string
}

// ── Step definitions ──────────────────────────────────────────────────────────

const FIRST_RUN_STEPS: WizardStep[] = [
  // --- About you (user.md) ---
  {
    key: 'user_name',
    question: () => `Hey! I'm your AI assistant. Before we get started, let me learn a bit about you.\n\nWhat's your name?`,
    placeholder: 'Your name…',
  },
  {
    key: 'user_tone',
    question: (a) => `Nice to meet you, ${a.user_name}! How do you like to communicate — casual and relaxed, or direct and straight to the point?`,
    placeholder: 'e.g. casual, direct, mix of both…',
  },
  {
    key: 'user_use',
    question: () => `What are you mainly going to use me for? (coding, writing, research, general chat, work tasks…)`,
    placeholder: 'e.g. coding and work tasks…',
  },
  // --- About the AI (soul.md + identity.md) ---
  {
    key: 'ai_name',
    question: (a) => `Got it! Now let's set up how I present myself.\n\nWhat do you want to call me? (default is "Aria")`,
    placeholder: 'e.g. Aria, Max, Nova…',
  },
  {
    key: 'ai_role',
    question: (a) => `Great — I'll go by ${a.ai_name || 'Aria'}. How do you think of me? (e.g. assistant, co-pilot, coding partner, creative collaborator)`,
    placeholder: 'e.g. coding partner, assistant…',
  },
  {
    key: 'ai_personality',
    question: () => `How should I come across? Pick words that fit. (e.g. warm and witty, professional and precise, casual and encouraging)`,
    placeholder: 'e.g. warm and direct, a little snarky…',
  },
  {
    key: 'ai_boundaries',
    question: () => `Any topics or behaviours I should avoid? (or just say "none")`,
    placeholder: 'e.g. none, keep things professional…',
  },
  {
    key: 'ai_extra',
    question: (a) => `Almost done! Anything else I should know — about you or about how you want ${a.ai_name || 'Aria'} to behave? (or say "that's it")`,
    placeholder: 'Anything else…',
  },
]

const SOUL_STEPS: WizardStep[] = [
  {
    key: 'ai_name',
    question: () => `Let's update my personality. What do you want to call me?`,
    placeholder: 'e.g. Aria, Nova, Max…',
  },
  {
    key: 'ai_role',
    question: (a) => `How do you think of ${a.ai_name || 'me'}? (e.g. assistant, coding partner, creative collaborator)`,
    placeholder: 'e.g. coding partner…',
  },
  {
    key: 'ai_personality',
    question: () => `How should I come across? (e.g. warm and witty, direct and precise, casual and snarky)`,
    placeholder: 'e.g. warm and direct…',
  },
  {
    key: 'ai_boundaries',
    question: () => `Any topics or behaviours I should avoid? (or say "none")`,
    placeholder: 'e.g. none…',
  },
]

const USER_STEPS: WizardStep[] = [
  {
    key: 'user_name',
    question: () => `Let's update your profile. What's your name?`,
    placeholder: 'Your name…',
  },
  {
    key: 'user_tone',
    question: (a) => `How do you like to communicate, ${a.user_name}? (casual, direct, formal, mix…)`,
    placeholder: 'e.g. direct and casual…',
  },
  {
    key: 'user_use',
    question: () => `What do you mainly use me for?`,
    placeholder: 'e.g. coding, writing, research…',
  },
  {
    key: 'user_extra',
    question: (a) => `Anything else I should know about you, ${a.user_name}? (or say "nothing else")`,
    placeholder: 'Anything else…',
  },
]

const IDENTITY_STEPS: WizardStep[] = [
  {
    key: 'ai_name',
    question: () => `What do you want to call me?`,
    placeholder: 'e.g. Aria, Nova, Max…',
  },
  {
    key: 'ai_role',
    question: (a) => `How do you think of ${a.ai_name || 'me'}? Give me a one-liner. (e.g. "your AI wife", "coding co-pilot")`,
    placeholder: 'e.g. AI co-pilot…',
  },
  {
    key: 'ai_vibe',
    question: () => `One sentence for my vibe / tagline?`,
    placeholder: 'e.g. Warm but direct. Gets stuff done.',
  },
]

// ── Content builders ──────────────────────────────────────────────────────────

function buildSoulMd(a: Record<string, string>): string {
  const name = a.ai_name || 'Aria'
  const role = a.ai_role || 'AI assistant'
  const personality = a.ai_personality || 'helpful and direct'
  const boundaries = (!a.ai_boundaries || a.ai_boundaries.toLowerCase() === 'none') ? 'None specified.' : a.ai_boundaries
  const extra = a.ai_extra && !['nothing', "that's it", 'nope', 'no'].some(s => a.ai_extra.toLowerCase().includes(s))
    ? `\n## Extra Context\n${a.ai_extra}` : ''

  return `# SOUL.md — ${name}'s Personality

## Core Identity
- **Name:** ${name}
- **Role:** ${role}
- **Personality:** ${personality}

## Behaviour
Be ${personality}. Skip filler phrases like "Great question!" — just do the thing. Have opinions. Be resourceful before asking.

## Boundaries
${boundaries}
${extra}

## Continuity
Each session, read the user profile and memory files to pick up where you left off.
`
}

function buildUserMd(a: Record<string, string>): string {
  const name = a.user_name || 'User'
  const tone = a.user_tone || 'direct'
  const use = a.user_use || 'general tasks'
  const extra = a.user_extra && !['nothing', 'nothing else', 'nope', 'no'].some(s => a.user_extra.toLowerCase().includes(s))
    ? `\n## Notes\n${a.user_extra}` : ''

  return `# USER.md — About the User

- **Name:** ${name}
- **What to call them:** ${name}
- **Communication style:** ${tone}
- **Primary use:** ${use}
- **Onboarded:** ${new Date().toISOString()}
${extra}
`
}

function buildIdentityMd(a: Record<string, string>): string {
  const name = a.ai_name || 'Aria'
  const role = a.ai_role || 'AI assistant'
  const vibe = a.ai_vibe || 'Helpful, direct, gets stuff done.'

  return `# IDENTITY.md

- **Name:** ${name}
- **Creature:** ${role}
- **Vibe:** ${vibe}
`
}

// ── Wizard component ──────────────────────────────────────────────────────────

function IdentityWizard({
  mode,
  aiName: initialAiName,
  onComplete,
  onDismiss,
}: {
  mode: WizardMode
  aiName: string
  onComplete: (aiName?: string) => void
  onDismiss?: () => void
}) {
  const steps = mode === 'firstrun' ? FIRST_RUN_STEPS
    : mode === 'soul' ? SOUL_STEPS
    : mode === 'user' ? USER_STEPS
    : IDENTITY_STEPS

  const titles: Record<WizardMode, string> = {
    firstrun: 'Welcome! Let\'s get set up',
    soul: 'Update AI Personality',
    user: 'Update Your Profile',
    identity: 'Update AI Identity',
  }
  const subtitles: Record<WizardMode, string> = {
    firstrun: `${steps.length} quick questions`,
    soul: `${steps.length} questions`,
    user: `${steps.length} questions`,
    identity: `${steps.length} questions`,
  }

  const [msgs, setMsgs] = useState<WizardMsg[]>([{
    role: 'ai',
    content: steps[0].question({}),
  }])
  const [stepIdx, setStepIdx] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [input, setInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [done, setDone] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])
  useEffect(() => { if (!saving) inputRef.current?.focus() }, [stepIdx, saving])

  const submit = async () => {
    const val = input.trim()
    if (!val || saving || done) return
    setInput('')

    const step = steps[stepIdx]
    const newAnswers = { ...answers, [step.key]: val }
    setAnswers(newAnswers)
    setMsgs(prev => [...prev, { role: 'user', content: val }])

    const nextIdx = stepIdx + 1
    if (nextIdx < steps.length) {
      setStepIdx(nextIdx)
      setTimeout(() => {
        setMsgs(prev => [...prev, { role: 'ai', content: steps[nextIdx].question(newAnswers) }])
      }, 350)
    } else {
      // All answered — build files and save
      const finalAiName = newAnswers.ai_name || initialAiName

      setTimeout(async () => {
        const outro = mode === 'firstrun'
          ? `Perfect. Everything's set up, ${newAnswers.user_name || 'friend'}. Let's go.`
          : mode === 'user'
          ? `Got it. Your profile is updated.`
          : mode === 'soul'
          ? `Done. I'll act accordingly from now on.`
          : `Done. I'm ${finalAiName} now.`

        setMsgs(prev => [...prev, { role: 'ai', content: outro }])
        setSaving(true)

        try {
          if (mode === 'firstrun') {
            await fetch(`${API_BASE}/v1/identity/setup`, {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({
                soul: buildSoulMd(newAnswers),
                user: buildUserMd(newAnswers),
                identity: buildIdentityMd(newAnswers),
              }),
            })
          } else if (mode === 'soul') {
            await fetch(`${API_BASE}/v1/identity/soul`, {
              method: 'PUT',
              headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ content: buildSoulMd(newAnswers) }),
            })
            // Also update identity if name changed
            await fetch(`${API_BASE}/v1/identity/identity-file`, {
              method: 'PUT',
              headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ content: buildIdentityMd(newAnswers) }),
            })
          } else if (mode === 'user') {
            await fetch(`${API_BASE}/v1/identity/user`, {
              method: 'PUT',
              headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ content: buildUserMd(newAnswers) }),
            })
          } else if (mode === 'identity') {
            await fetch(`${API_BASE}/v1/identity/identity-file`, {
              method: 'PUT',
              headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ content: buildIdentityMd(newAnswers) }),
            })
            // Keep soul in sync with any name change
            await fetch(`${API_BASE}/v1/identity/soul`, {
              method: 'PUT',
              headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ content: buildSoulMd(newAnswers) }),
            })
          }
        } catch (e) {
          console.error('Wizard save failed', e)
        }

        setDone(true)
        setTimeout(() => onComplete(finalAiName), 1200)
      }, 350)
    }
  }

  const progress = Math.round(((stepIdx) / steps.length) * 100)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl flex flex-col overflow-hidden" style={{ maxHeight: '85vh' }}>

        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-orange-100 dark:bg-orange-900/40 flex items-center justify-center text-lg">✦</div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">{titles[mode]}</p>
              <p className="text-xs text-gray-400">{subtitles[mode]}</p>
            </div>
          </div>
          {onDismiss && !saving && (
            <button onClick={onDismiss} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 text-lg leading-none">✕</button>
          )}
        </div>

        {/* Progress bar */}
        {!done && (
          <div className="h-1 bg-gray-100 dark:bg-gray-800">
            <div
              className="h-1 bg-orange-400 transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 min-h-0">
          {msgs.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                m.role === 'ai'
                  ? 'bg-orange-50 dark:bg-orange-900/20 border border-orange-100 dark:border-orange-800 text-gray-800 dark:text-gray-100 rounded-tl-sm'
                  : 'bg-indigo-600 text-white rounded-tr-sm'
              }`}>
                {m.content}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        {!saving && !done && (
          <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 flex gap-2">
            <input
              ref={inputRef}
              autoFocus
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submit()}
              placeholder={steps[stepIdx]?.placeholder || 'Your answer…'}
              className="flex-1 rounded-xl border border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-white px-3.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent"
            />
            <button
              onClick={submit}
              disabled={!input.trim()}
              className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-200 dark:disabled:bg-gray-700 text-white disabled:text-gray-400 rounded-xl text-sm font-medium transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        )}
        {(saving || done) && (
          <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 text-center text-sm text-gray-400">
            {done ? '✓ All saved!' : 'Saving…'}
          </div>
        )}
      </div>
    </div>
  )
}

// Legacy alias so nothing else breaks
function OnboardingOverlay({ aiName, onComplete }: { aiName: string; onComplete: () => void }) {
  return <IdentityWizard mode="firstrun" aiName={aiName} onComplete={onComplete} />
}

// ─── Microphone (speech-to-text) button ──────────────────────────────────────
type MicState = 'idle' | 'recording' | 'processing'

function MicrophoneButton({ onTranscript, disabled }: { onTranscript: (text: string) => void; disabled?: boolean }) {
  const [micState, setMicState] = useState<MicState>('idle')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const silenceCheckRef = useRef<number | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopRecording(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const stopRecording = useCallback((skipTranscription = false) => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current)
    if (silenceCheckRef.current) cancelAnimationFrame(silenceCheckRef.current)
    silenceTimerRef.current = null
    silenceCheckRef.current = null

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      if (skipTranscription) {
        // Remove event listeners to prevent transcription
        mediaRecorderRef.current.onstop = null
      }
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {})
      audioCtxRef.current = null
    }
    analyserRef.current = null

    if (skipTranscription) {
      setMicState('idle')
      chunksRef.current = []
    }
  }, [])

  const transcribe = useCallback(async (blob: Blob) => {
    setMicState('processing')
    try {
      const formData = new FormData()
      formData.append('file', blob, 'recording.webm')

      const resp = await fetch(`${API_BASE}/v1/audio/transcribe`, {
        method: 'POST',
        headers: { Authorization: AUTH_HEADERS['Authorization'] },
        body: formData,
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail || `Transcription failed (${resp.status})`)
      }

      const data = await resp.json()
      if (data.text && data.text.trim()) {
        onTranscript(data.text.trim())
      }
    } catch (err: any) {
      console.error('Transcription error:', err)
      // Could show a toast here, but we keep it simple
    } finally {
      setMicState('idle')
    }
  }, [onTranscript])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Set up silence detection via AudioContext analyser
      const audioCtx = new AudioContext()
      audioCtxRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      analyser.smoothingTimeConstant = 0.8
      source.connect(analyser)
      analyserRef.current = analyser

      // Determine supported mime type
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : ''

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' })
        chunksRef.current = []
        if (blob.size > 0) {
          transcribe(blob)
        } else {
          setMicState('idle')
        }
      }

      recorder.start(250) // collect data every 250ms
      setMicState('recording')

      // Silence detection: auto-stop after 3s of silence
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      let silenceStart: number | null = null
      const SILENCE_THRESHOLD = 15 // RMS level below which we consider silence
      const SILENCE_DURATION = 3000 // ms

      const checkSilence = () => {
        if (!analyserRef.current) return
        analyserRef.current.getByteTimeDomainData(dataArray)

        // Calculate RMS
        let sum = 0
        for (let i = 0; i < dataArray.length; i++) {
          const v = (dataArray[i] - 128) / 128
          sum += v * v
        }
        const rms = Math.sqrt(sum / dataArray.length) * 100

        if (rms < SILENCE_THRESHOLD) {
          if (!silenceStart) silenceStart = Date.now()
          else if (Date.now() - silenceStart > SILENCE_DURATION) {
            // 3s of silence detected — stop recording
            stopRecording()
            return
          }
        } else {
          silenceStart = null
        }

        silenceCheckRef.current = requestAnimationFrame(checkSilence)
      }
      silenceCheckRef.current = requestAnimationFrame(checkSilence)
    } catch (err: any) {
      console.error('Microphone access error:', err)
      setMicState('idle')
    }
  }, [transcribe, stopRecording])

  const handleClick = () => {
    if (disabled || micState === 'processing') return
    if (micState === 'idle') {
      startRecording()
    } else if (micState === 'recording') {
      stopRecording()
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || micState === 'processing'}
      title={micState === 'idle' ? 'Voice input (speech-to-text)' : micState === 'recording' ? 'Stop recording' : 'Transcribing...'}
      className={`flex-shrink-0 p-2.5 rounded-xl border transition-colors ${
        micState === 'recording'
          ? 'bg-red-50 dark:bg-red-900/30 border-red-300 dark:border-red-600 text-red-500'
          : micState === 'processing'
            ? 'border-orange-300 dark:border-orange-600 text-orange-400'
            : 'border-gray-200 dark:border-gray-700 text-gray-400 hover:text-orange-500 hover:border-orange-300'
      } disabled:opacity-50`}
    >
      {micState === 'processing' ? (
        /* Spinner */
        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : (
        /* Microphone icon with pulsing dot when recording */
        <span className="relative">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
          </svg>
          {micState === 'recording' && (
            <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full animate-pulse" />
          )}
        </span>
      )}
    </button>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ChatPage() {
  const searchParams = useSearchParams()


  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])
  const [selectedPersonaId, setSelectedPersonaId] = useState('')
  const [models, setModels] = useState<Model[]>([])
  const [selectedModelId, setSelectedModelId] = useState('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(288)  // px; matches old w-72
  const [searchQuery, setSearchQuery] = useState('')
  const [searchDebounce, setSearchDebounce] = useState('')
  const [activeModelName, setActiveModelName] = useState<string>('')
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleValue, setTitleValue] = useState('')
  const [shareModal, setShareModal] = useState<{ url: string; expires_at: string | null } | null>(null)
  const [sharing, setSharing] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [userExists, setUserExists] = useState(true)   // assume true until checked
  const [aiName, setAiName] = useState('Aria')

  // ── Voice mode state ──────────────────────────────────────────────────────
  const [voiceModeActive, setVoiceModeActive] = useState(false)
  const [voiceWorkflowTrigger, setVoiceWorkflowTrigger] = useState<{
    method_id: string; method_name: string; score: number; is_custom: boolean;
  } | null>(null)
  const [voicePipelineId, setVoicePipelineId] = useState<string | null>(null)

  // ── Identity wizard state ─────────────────────────────────────────────────
  const [wizardMode, setWizardMode] = useState<WizardMode | null>(null)

  // ── Slash commands ────────────────────────────────────────────────────────
  const [slashOpen, setSlashOpen] = useState(false)
  const [slashFilter, setSlashFilter] = useState('')
  const [slashIndex, setSlashIndex] = useState(0)

  const SLASH_COMMANDS = [
    { cmd: '/help',        hint: '',            desc: 'Show all available commands' },
    { cmd: '/reset',       hint: '',            desc: 'Clear conversation and start fresh' },
    { cmd: '/onboard',     hint: '',            desc: 'Re-run full first-time setup wizard' },
    { cmd: '/soul',        hint: '',            desc: 'Update AI personality & soul' },
    { cmd: '/identity',    hint: '',            desc: 'Update AI name & identity' },
    { cmd: '/user',        hint: '',            desc: 'Update your profile (name, tone, use)' },
    { cmd: '/persona',     hint: '<name>',      desc: 'Switch active persona' },
    { cmd: '/model',       hint: '<model-id>',  desc: 'Override model for this conversation' },
    { cmd: '/image',       hint: '<prompt>',    desc: 'Generate an image' },
    { cmd: '/pin',         hint: '',            desc: 'Pin current conversation' },
    { cmd: '/export',      hint: '',            desc: 'Export conversation as markdown' },
    { cmd: '/theme',       hint: '',            desc: 'Toggle dark/light mode' },
    { cmd: '/clear',       hint: '',            desc: 'Clear chat display' },
    { cmd: '/settings',    hint: '',            desc: 'Open settings page' },
    { cmd: '/method',      hint: '<name>',      desc: 'Switch development method (bmad/gsd/superpowers/gtrack)' },
  ]

  const filteredCommands = SLASH_COMMANDS.filter(c =>
    c.cmd.startsWith('/' + slashFilter) || c.desc.toLowerCase().includes(slashFilter.toLowerCase())
  )

  const { submitTask, addToast } = useToast()

  const executeSlashCommand = useCallback(async (raw: string) => {
    const [cmd, ...args] = raw.trim().split(/\s+/)
    const arg = args.join(' ')

    switch (cmd) {
      case '/help': {
        const helpText = SLASH_COMMANDS.map(c => `**${c.cmd}** ${c.hint} — ${c.desc}`).join('\n')
        setMessages(prev => [...prev, {
          id: `help-${Date.now()}`, role: 'assistant' as const,
          content: `Available commands:\n\n${helpText}`,
          created_at: new Date().toISOString()
        }])
        break
      }
      case '/reset':
        setActiveConvId(null)
        setMessages([])
        setTitleValue('')
        window.history.replaceState(null, '', '/chat')
        localStorage.removeItem('devforge_last_session')
        break
      case '/clear':
        setMessages([])
        break
      case '/onboard':
        setWizardMode('firstrun')
        break
      case '/soul':
        setWizardMode('soul')
        break
      case '/identity':
        setWizardMode('identity')
        break
      case '/user':
        setWizardMode('user')
        break
      case '/pin':
        if (activeConvId) {
          await fetch(`${API_BASE}/v1/conversations/${activeConvId}`, {
            method: 'PATCH', headers: AUTH_HEADERS, body: JSON.stringify({ pinned: true })
          })
          setConversations(prev => prev.map(c => c.id === activeConvId ? { ...c, pinned: true } : c))
          addToast({ type: 'success', title: 'Pinned', message: 'Conversation pinned.', autoClose: 2000 })
        }
        break
      case '/theme': {
        const isDark = document.documentElement.classList.contains('dark')
        document.documentElement.classList.toggle('dark', !isDark)
        localStorage.setItem('theme', isDark ? 'light' : 'dark')
        break
      }
      case '/settings':
        window.location.href = '/settings'
        break
      case '/image':
        if (arg) {
          // Pre-fill prompt and auto-submit
          setImagePrompt(arg)
          setShowImageGen(true)
          // Small delay to let state settle, then fire generation
          setTimeout(() => generateImage(arg), 50)
        } else {
          setShowImageGen(true)
        }
        break
      case '/persona': {
        if (arg) {
          const match = personas.find(p => p.name.toLowerCase().includes(arg.toLowerCase()))
          if (match) {
            setSelectedPersonaId(match.id)
            addToast({ type: 'success', title: 'Persona switched', message: `Now using ${match.name}`, autoClose: 2000 })
          } else {
            addToast({ type: 'error', title: 'Not found', message: `No persona matching "${arg}"`, autoClose: 3000 })
          }
        }
        break
      }
      case '/model': {
        if (arg) {
          const match = personas.find(p => p.name.toLowerCase().includes(arg.toLowerCase()) || p.id === arg)
          if (match) {
            setSelectedPersonaId(match.id)
            addToast({ type: 'success', title: 'Model switched', message: match.name, autoClose: 2000 })
          } else {
            addToast({ type: 'error', title: 'Not found', message: `No match for "${arg}"`, autoClose: 3000 })
          }
        }
        break
      }
      case '/method': {
        // Redirect to methods page (full implementation in progress)
        window.location.href = '/methods'
        break
      }
      case '/export': {
        if (messages.length === 0) break
        const md = messages.map(m => `**${m.role === 'user' ? 'You' : 'AI'}:** ${m.content}`).join('\n\n')
        const blob = new Blob([md], { type: 'text/markdown' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `conversation-${activeConvId || Date.now()}.md`
        a.click()
        URL.revokeObjectURL(url)
        break
      }
    }
  }, [activeConvId, messages, personas, addToast, setUserExists])

  const [showImageGen, setShowImageGen] = useState(false)
  const [imagePrompt, setImagePrompt] = useState('')
  const [generatingImage, setGeneratingImage] = useState(false)
  const [imageProvider, setImageProvider] = useState<'gemini-imagen' | 'comfyui-local'>('gemini-imagen')

  // Workflow list for ComfyUI — user picks one saved workflow, nothing else.
  // To change checkpoint/LoRA/size/negative prompt, edit and save the workflow in ComfyUI.
  const [workflows, setWorkflows] = useState<Array<{id: string, name: string, description: string, category: string}>>([])
  const [selectedWorkflowId, setSelectedWorkflowId] = useState('sdxl-standard')
  const [comfyStatus, setComfyStatus] = useState<'online' | 'offline' | 'checking'>('checking')

  // Track pending image tasks: taskId → assistantMessageId
  const pendingImageTasksRef = useRef<Map<string, string | { msgId: string; startedAt: number }>>(new Map())
  const IMAGE_TASK_SLOW_WARNING_MS = 12 * 60 * 1000
  const IMAGE_TASK_HARD_TIMEOUT_MS = 45 * 60 * 1000

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const imagePromptRef = useRef<HTMLTextAreaElement>(null)
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()

  // ── Fetch available workflows when image gen opens ──────────────────────
  useEffect(() => {
    if (!showImageGen) return
    const load = async () => {
      try {
        const [wfRes, stRes] = await Promise.all([
          fetch(`${API_BASE}/v1/workflows`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
          fetch(`${API_BASE}/v1/comfyui/status`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ status: 'offline' })),
        ])
        setWorkflows(wfRes.data || [])
        setComfyStatus(stRes.status === 'online' ? 'online' : 'offline')
        // Default to the first workflow if current selection isn't in the list
        if (wfRes.data?.length > 0 && !wfRes.data.find((w: any) => w.id === selectedWorkflowId)) {
          setSelectedWorkflowId(wfRes.data[0].id)
        }
      } catch { /* silent */ }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showImageGen])

  // ── Poll for image task completion → inject inline ────────────────────────
  // Helper to handle a completed image task
  const handleImageTaskComplete = useCallback((taskId: string, msgId: string, imageUrl: string, relativeUrl: string) => {
    setMessages(prev => prev.map(m =>
      m.id === msgId
        ? { ...m, content: '🖼️ Here\'s your image:', image_url: imageUrl, streaming: false }
        : m
    ))
    pendingImageTasksRef.current.delete(taskId)
    fetch(`${API_BASE}/v1/tasks/${taskId}/acknowledge`, { method: 'POST', headers: AUTH_HEADERS }).catch(() => {})
    // Persist image URL + updated content to DB so it works on reload
    fetch(`${API_BASE}/v1/conversations/messages/${msgId}/image`, {
      method: 'PATCH', headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_url: relativeUrl, content: '🖼️ Here\'s your image:' })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const poll = async () => {
      if (pendingImageTasksRef.current.size === 0) return

      const now = Date.now()
      const entries = Array.from(pendingImageTasksRef.current.entries())
      for (const [taskId, value] of entries) {
        // Support both old format (string msgId) and new format ({msgId, startedAt})
        const msgId = typeof value === 'string' ? value : value.msgId
        const startedAt = typeof value === 'string' ? now : value.startedAt

        const elapsedMs = now - startedAt

        // Hard timeout for truly stuck jobs.
        if (elapsedMs > IMAGE_TASK_HARD_TIMEOUT_MS) {
          setMessages(prev => prev.map(m =>
            m.id === msgId
              ? { ...m, content: '⏱️ Image generation timed out. Try again.', streaming: false }
              : m
          ))
          pendingImageTasksRef.current.delete(taskId)
          continue
        }

        // Soft warning for slow but still valid jobs (e.g., RAM offload).
        if (elapsedMs > IMAGE_TASK_SLOW_WARNING_MS) {
          setMessages(prev => prev.map(m =>
            m.id === msgId && !m.content.includes('still running')
              ? { ...m, content: '⏳ Still running… this can take longer when ComfyUI offloads to system RAM.' }
              : m
          ))
        }

        try {
          const res = await fetch(`${API_BASE}/v1/tasks/${taskId}`, { headers: AUTH_HEADERS })
          if (!res.ok) continue
          const task = await res.json()
          if (task.status === 'completed' && task.result?.url) {
            const imageUrl = `${API_BASE}${task.result.url}`
            handleImageTaskComplete(taskId, msgId, imageUrl, task.result.url)
          } else if (task.status === 'failed') {
            setMessages(prev => prev.map(m =>
              m.id === msgId
                ? { ...m, content: `❌ Image generation failed: ${task.error || 'Unknown error'}`, streaming: false }
                : m
            ))
            pendingImageTasksRef.current.delete(taskId)
          } else if (task.user_message) {
            // Running/pending — show live progress from the backend
            const progress = task.progress ? ` (${task.progress}%)` : ''
            const statusContent = `🎨 ${task.user_message}${progress}`
            setMessages(prev => prev.map(m =>
              m.id === msgId && m.content !== statusContent
                ? { ...m, content: statusContent }
                : m
            ))
          }
        } catch { /* silent — will retry next cycle */ }
      }
    }
    // Poll faster while any task is pending — shows live ComfyUI progress
    const interval = setInterval(poll, 1500)
    return () => clearInterval(interval)
  }, [handleImageTaskComplete])

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const init = async () => {
      try {
        const [modelsRes, personasRes, convsRes, identityRes] = await Promise.all([
          fetch(`${API_BASE}/v1/models?active_only=true&usable_only=true&validated_only=true&chat_only=true`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
          fetch(`${API_BASE}/v1/personas`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
          fetch(`${API_BASE}/v1/conversations?limit=100&pinned_first=true`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
          fetch(`${API_BASE}/v1/identity/status`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({})),
        ])

        const ps: Persona[] = personasRes.data || []
        setPersonas(ps)
        const ms: Model[] = (modelsRes.data || []).filter((m: Model) => m.is_active)
        setModels(ms)

        const defaultP = ps.find(p => p.is_default) || ps[0]
        if (defaultP) setSelectedPersonaId(defaultP.id)

        const convs: Conversation[] = convsRes.data || []
        setConversations(convs)

        // Set AI name from soul.md if available
        if (identityRes.ai_name) setAiName(identityRes.ai_name)

        // Show first-run wizard if setup is incomplete
        if (identityRes.first_run) {
          setWizardMode('firstrun')
        } else {
          setUserExists(true)
          // Restore from URL or last session
          const sessionParam = searchParams?.get('session')
          const lastId = localStorage.getItem('devforge_last_session')
          const targetId = sessionParam || lastId
          if (targetId) {
            // Load the session even if it's not in the conversation list yet —
            // it might have been created moments ago and not yet in the first page
            const inList = convs.find(c => c.id === targetId)
            if (inList) {
              loadSession(targetId, convs, ps)
            } else {
              // Try fetching the conversation directly — it exists in DB but
              // wasn't in the list (just created, or past the limit)
              try {
                const checkRes = await fetch(`${API_BASE}/v1/conversations/${targetId}/messages?limit=1`, { headers: AUTH_HEADERS })
                if (checkRes.ok) {
                  // Conversation exists — add stub to list and load it
                  const stub: Conversation = {
                    id: targetId, title: 'Loading…', pinned: false, keep_forever: false,
                    last_message_at: new Date().toISOString(), message_count: 0,
                    created_at: new Date().toISOString(), persona_id: ps[0]?.id || '',
                  }
                  setConversations(prev => [stub, ...prev])
                  loadSession(targetId, [stub, ...convs], ps)
                }
              } catch { /* conversation truly doesn't exist — start fresh */ }
            }
          }
        }
      } catch (e) {
        console.error('Init failed:', e)
      }
    }
    init()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load saved sidebar width on mount
  useEffect(() => {
    const saved = localStorage.getItem('devforge_sidebar_width')
    if (saved) {
      const n = parseInt(saved, 10)
      if (!isNaN(n) && n >= 240 && n <= 560) setSidebarWidth(n)
    }
    const savedCollapsed = localStorage.getItem('devforge_chat_sidebar_collapsed')
    if (savedCollapsed === 'true') setSidebarCollapsed(true)
  }, [])

  // Persist sidebar state
  useEffect(() => {
    localStorage.setItem('devforge_sidebar_width', String(sidebarWidth))
  }, [sidebarWidth])
  useEffect(() => {
    localStorage.setItem('devforge_chat_sidebar_collapsed', String(sidebarCollapsed))
  }, [sidebarCollapsed])

  // ── Keep sidebar in sync — refresh on window focus and periodically ─────
  useEffect(() => {
    const onFocus = () => refreshConversations()
    window.addEventListener('focus', onFocus)
    // Also refresh every 30s in case conversations were created in another tab
    const interval = setInterval(refreshConversations, 30_000)
    return () => { window.removeEventListener('focus', onFocus); clearInterval(interval) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Search debounce ───────────────────────────────────────────────────────
  useEffect(() => {
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setSearchDebounce(searchQuery), 300)
  }, [searchQuery])

  // ── Filtered conversations ────────────────────────────────────────────────
  const filteredConvs = searchDebounce
    ? conversations.filter(c => (c.title || '').toLowerCase().includes(searchDebounce.toLowerCase()))
    : conversations

  // ── Scroll to bottom ──────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Textarea auto-resize ──────────────────────────────────────────────────
  // Grows with content up to ~40% of viewport height, then internal scroll.
  useEffect(() => {
    if (textareaRef.current) {
      const maxH = Math.max(200, Math.floor(window.innerHeight * 0.4))
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, maxH) + 'px'
    }
  }, [input])

  // Image prompt auto-resize (same behavior as chat textarea)
  useEffect(() => {
    if (imagePromptRef.current) {
      const maxH = Math.max(200, Math.floor(window.innerHeight * 0.4))
      imagePromptRef.current.style.height = 'auto'
      imagePromptRef.current.style.height = Math.min(imagePromptRef.current.scrollHeight, maxH) + 'px'
    }
  }, [imagePrompt, showImageGen])

  // ── Load session ──────────────────────────────────────────────────────────
  const [recoverySnapshot, setRecoverySnapshot] = useState<{conversationId: string, summary: string, messageCount: number} | null>(null)

  const loadSession = useCallback(async (id: string, convList?: Conversation[], personaList?: Persona[]) => {
    setActiveConvId(id)
    setLoadingMessages(true)
    setRecoverySnapshot(null)
    localStorage.setItem('devforge_last_session', id)
    window.history.replaceState(null, '', `/chat?session=${id}`)

    // Update title input and restore persona from conversation
    const conv = (convList || conversations).find(c => c.id === id)
    setTitleValue(conv?.title || '')
    if (conv?.persona_id && (personaList || personas).find(p => p.id === conv.persona_id)) {
      setSelectedPersonaId(conv.persona_id)
    }

    try {
      const res = await fetch(`${API_BASE}/v1/conversations/${id}/messages?limit=200`, { headers: AUTH_HEADERS })
      const data = await res.json()
      const msgs: Message[] = (data.data || []).map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        created_at: m.created_at,
        // Handle both relative (/v1/img/...) and already-absolute URLs
        image_url: m.image_url
          ? (m.image_url.startsWith('http') ? m.image_url : `${API_BASE}${m.image_url}`)
          : undefined,
      }))
      setMessages(msgs)

      // If DB came back empty, check for a context snapshot to offer recovery
      if (msgs.length === 0) {
        try {
          const snapRes = await fetch(`${API_BASE}/v1/context/recover/${id}`, { headers: AUTH_HEADERS })
          if (snapRes.ok) {
            const snapData = await snapRes.json()
            if (snapData.message_count > 0 || snapData.snapshot) {
              setRecoverySnapshot({
                conversationId: id,
                summary: snapData.recovery_summary || '',
                messageCount: snapData.message_count || 0,
              })
            }
          }
        } catch { /* no snapshot available, that's fine */ }
      }
    } catch (e) {
      console.error('Failed to load messages:', e)
      setMessages([])
    } finally {
      setLoadingMessages(false)
    }
  }, [conversations])

  // ── New chat ──────────────────────────────────────────────────────────────
  const newChat = () => {
    // Just clear local state — conversation is created on first message, not before
    setActiveConvId(null)
    setMessages([])
    setTitleValue('')
    window.history.replaceState(null, '', '/chat')
    localStorage.removeItem('devforge_last_session')
    textareaRef.current?.focus()
  }

  // ── Send message ──────────────────────────────────────────────────────────
  // Detect image generation intent from natural language
  const detectImageIntent = (text: string): string | null => {
    const lower = text.toLowerCase()
    const imageVerbs = ['generate', 'create', 'make', 'draw', 'paint', 'render', 'design', 'produce', 'show me']
    const imageNouns = ['image', 'picture', 'photo', 'illustration', 'artwork', 'drawing', 'painting', 'portrait', 'wallpaper', 'logo', 'icon', 'banner']
    const hasVerb = imageVerbs.some(v => lower.includes(v))
    const hasNoun = imageNouns.some(n => lower.includes(n))
    if (hasVerb && hasNoun) return text
    // Also catch "/imagine" style
    if (lower.startsWith('/imagine ') || lower.startsWith('/img ')) return text.split(' ').slice(1).join(' ')
    return null
  }

  const sendMessage = async (directText?: string) => {
    const text = directText?.trim() || input.trim()
    if (!text || loading) return
    if (!directText) setInput('')

    // Intercept slash commands before sending to AI
    if (text.startsWith('/')) {
      await executeSlashCommand(text)
      return
    }

    // Route to image generation if intent detected
    const imagePromptDetected = detectImageIntent(text)
    if (imagePromptDetected) {
      generateImage(imagePromptDetected)
      return
    }

    const userMsg: Message = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    // Placeholder assistant message for streaming
    const assistantId = `stream-${Date.now()}`
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      streaming: true,
    }
    setMessages(prev => [...prev, assistantMsg])

    const historyMsgs = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }))

    try {
      const body: any = {
        model: selectedPersonaId,
        messages: historyMsgs,
        stream: false,
        ...(selectedModelId ? { model_override: selectedModelId } : {}),
      }
      if (activeConvId) body.conversation_id = activeConvId

      const res = await fetch(`${API_BASE}/v1/chat/completions`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify(body),
      })

      const data = await res.json()

      if (!res.ok) {
        throw new Error(data?.detail?.error?.message || data?.detail || `Request failed (${res.status})`)
      }

      const fullContent = data.choices?.[0]?.message?.content || ''
      const modelName = data.model || ''
      const convId = data.conversation_id || data.modelmesh?.conversation_id || activeConvId

      // Extract workflow trigger metadata for voice mode
      const wfTrigger = data.modelmesh?.workflow_trigger || null
      if (voiceModeActive) {
        setVoiceWorkflowTrigger(wfTrigger)
        // Detect pipeline ID from "Pipeline ID: `xxx`" in response
        const pidMatch = fullContent.match(/\*\*Pipeline ID:\*\*\s*`([^`]+)`/)
        if (pidMatch) setVoicePipelineId(pidMatch[1])
      }

      // Update assistant message
      setMessages(prev => prev.map(m =>
        m.id === assistantId
          ? { ...m, content: fullContent || '(no response)', streaming: false, model: modelName }
          : m
      ))
      setActiveModelName(modelName)

      // Update conversation state
      if (convId && convId !== activeConvId) {
        // Set all React state BEFORE URL update
        const autoTitle = text.slice(0, 60) + (text.length > 60 ? '...' : '')
        setActiveConvId(convId)
        setConversations(prev => {
          if (prev.some(c => c.id === convId)) return prev
          return [{
            id: convId!,
            title: autoTitle,
            pinned: false,
            keep_forever: false,
            last_message_at: new Date().toISOString(),
            message_count: 2,
            created_at: new Date().toISOString(),
            persona_id: selectedPersonaId,
          }, ...prev]
        })
        setTitleValue(autoTitle)
        // Update URL + localStorage AFTER state is queued
        localStorage.setItem('devforge_last_session', convId)
        window.history.replaceState(null, '', `/chat?session=${convId}`)
        // Delay refresh so the DB commit is fully visible to the list query
        setTimeout(() => refreshConversations(), 800)
      } else if (convId) {
        // Auto-title on first real message (replaces "New Chat" placeholder)
        const conv = conversations.find(c => c.id === convId)
        const needsTitle = conv && (!conv.title || conv.title === 'New Chat')
        const autoTitle = needsTitle ? text.slice(0, 60) + (text.length > 60 ? '...' : '') : null
        setConversations(prev => prev.map(c =>
          c.id === convId ? {
            ...c,
            last_message_at: new Date().toISOString(),
            message_count: (c.message_count || 0) + 2,
            ...(autoTitle ? { title: autoTitle } : {}),
          } : c
        ))
        if (autoTitle) {
          setTitleValue(autoTitle)
          fetch(`${API_BASE}/v1/conversations/${convId}`, {
            method: 'PATCH', headers: AUTH_HEADERS, body: JSON.stringify({ title: autoTitle })
          }).catch(() => {})
        }
      }

    } catch (e: any) {
      setMessages(prev => prev.map(m =>
        m.id === assistantId
          ? { ...m, content: `Error: ${e.message}`, streaming: false }
          : m
      ))
    } finally {
      setLoading(false)
      textareaRef.current?.focus()
    }
  }

  // ─── Voice mode: send transcribed text directly ─────────────────────────
  const sendVoiceMessage = useCallback((text: string) => {
    if (!text.trim()) return
    sendMessage(text.trim())
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ─── Track last assistant message for voice mode TTS ────────────────────
  const lastAssistantMessage = messages.length > 0
    ? [...messages].reverse().find(m => m.role === 'assistant' && !m.streaming && m.content && !m.content.startsWith('Error:'))?.content ?? null
    : null

  const generateImage = async (overridePrompt?: string) => {
    const prompt = (overridePrompt ?? imagePrompt).trim()
    if (!prompt || generatingImage) return
    setGeneratingImage(true)
    setShowImageGen(false)

    const provider = imageProvider
    const wfId = provider === 'comfyui-local' ? selectedWorkflowId : undefined
    const wfName = workflows.find(w => w.id === wfId)?.name
    // Gemini-only size. For ComfyUI, size comes from the workflow.
    const size = provider === 'comfyui-local' ? undefined : '1024x1024'

    setImagePrompt('')

    // Add user + placeholder messages to local state
    const userMsg: Message = {
      id: `img-user-${Date.now()}`,
      role: 'user' as const,
      content: `🖼️ Generate image: ${prompt}`,
      created_at: new Date().toISOString(),
    }
    const assistantId = `img-${Date.now()}`
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant' as const,
      content: `🎨 Generating image${wfName ? ` with ${wfName}` : ''}…`,
      streaming: true,
      created_at: new Date().toISOString(),
      image_meta: provider === 'comfyui-local'
        ? { provider: 'ComfyUI', workflow: wfName || wfId || '', checkpoint: '' }
        : { provider: 'Gemini', workflow: '', checkpoint: '' },
    }
    setMessages(prev => [...prev, userMsg, assistantMsg])

    // Ensure we have a conversation for this image request
    try {
      let convId: string | null = activeConvId
      const autoTitle = `🖼️ ${prompt.slice(0, 50)}${prompt.length > 50 ? '...' : ''}`

      // Create conversation if we don't have one
      if (!convId) {
        const createRes = await fetch(`${API_BASE}/v1/conversations`, {
          method: 'POST',
          headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: autoTitle,
            persona_id: selectedPersonaId || undefined,
          })
        }).then(r => r.json())
        convId = createRes.id || createRes.data?.id || null
      }

      // Always ensure the conversation is in the sidebar BEFORE URL update
      if (convId) {
        if (convId !== activeConvId) setActiveConvId(convId)
        setConversations(prev => {
          if (prev.some(c => c.id === convId)) {
            // Already exists — update title
            return prev.map(c =>
              c.id === convId ? { ...c, title: autoTitle, last_message_at: new Date().toISOString() } : c
            )
          }
          // New — prepend
          return [{
            id: convId!,
            title: autoTitle,
            pinned: false,
            keep_forever: false,
            last_message_at: new Date().toISOString(),
            message_count: 1,
            created_at: new Date().toISOString(),
            persona_id: selectedPersonaId,
          }, ...prev]
        })
        setTitleValue(autoTitle)
        // URL + localStorage AFTER state is queued
        if (convId !== activeConvId) {
          localStorage.setItem('devforge_last_session', convId)
          window.history.replaceState(null, '', `/chat?session=${convId}`)
        }
        // Update backend title
        fetch(`${API_BASE}/v1/conversations/${convId}`, {
          method: 'PATCH', headers: AUTH_HEADERS, body: JSON.stringify({ title: autoTitle })
        }).catch(() => {})
      }

      // Save user message + assistant placeholder to DB
      let dbAssistantId = assistantId
      if (convId) {
        try {
          // Save user message
          await fetch(`${API_BASE}/v1/conversations/${convId}/messages`, {
            method: 'POST', headers: AUTH_HEADERS,
            body: JSON.stringify({ role: 'user', content: `🖼️ Generate image: ${prompt}` })
          })
          // Save assistant placeholder — get its DB ID for image_url patching
          const assistantRes = await fetch(`${API_BASE}/v1/conversations/${convId}/messages`, {
            method: 'POST', headers: AUTH_HEADERS,
            body: JSON.stringify({
              role: 'assistant',
              content: `🎨 Generating image${wfName ? ` with ${wfName}` : ''}…`,
            })
          }).then(r => r.json())
          if (assistantRes.id) {
            dbAssistantId = assistantRes.id
            setMessages(prev => prev.map(m =>
              m.id === assistantId ? { ...m, id: dbAssistantId } : m
            ))
          }
        } catch { /* non-fatal — image still generates */ }
      }

      const taskPayload: any = {
        prompt,
        model: provider,
        format: 'png',
      }
      // ComfyUI: size/checkpoint/LoRA/negative prompt come from the saved workflow.
      // Gemini: we set size here (workflow has no equivalent concept).
      if (size) taskPayload.size = size
      if (wfId) taskPayload.workflow_id = wfId

      const taskId = await submitTask('image_gen', taskPayload, convId || undefined)
      // Map task → message so we can inject the image inline when done (use real DB ID)
      pendingImageTasksRef.current.set(taskId, { msgId: dbAssistantId, startedAt: Date.now() })
      
      // Poll immediately after task submission (for fast providers that complete within 3s)
      setTimeout(() => {
        const rawVal = pendingImageTasksRef.current.get(taskId)
        if (!rawVal) return
        const msgId = typeof rawVal === 'string' ? rawVal : rawVal.msgId
        fetch(`${API_BASE}/v1/tasks/${taskId}`, { headers: AUTH_HEADERS })
          .then(r => r.ok ? r.json() : null)
          .then(task => {
            if (task?.status === 'completed' && task.result?.url) {
              handleImageTaskComplete(taskId, msgId, `${API_BASE}${task.result.url}`, task.result.url)
            }
          })
          .catch(() => {})
      }, 500)
    } catch (e: any) {
      addToast({
        type: 'error',
        title: 'Image submission failed',
        message: e.message,
        autoClose: 6000,
      })
    } finally {
      setGeneratingImage(false)
    }
  }
  const refreshConversations = async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/conversations?limit=100&pinned_first=true`, { headers: AUTH_HEADERS })
      if (!res.ok) return
      const data = await res.json()
      const fresh: Conversation[] = data.data || []
      if (fresh.length === 0) return // backend returned empty — keep current list
      setConversations(prev => {
        // Merge: use fresh list as base, but preserve any local-only entries
        // (conversations just created that might not be in the DB response yet)
        const freshIds = new Set(fresh.map(c => c.id))
        const localOnly = prev.filter(c => !freshIds.has(c.id))
        return [...localOnly, ...fresh]
      })
    } catch { /* network error — keep current sidebar intact */ }
  }

  // ── Conversation actions ──────────────────────────────────────────────────
  const deleteConv = async (id: string) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, { method: 'DELETE', headers: AUTH_HEADERS })
    setConversations(prev => prev.filter(c => c.id !== id))
    if (activeConvId === id) newChat()
  }

  const pinConv = async (id: string, val: boolean) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, {
      method: 'PATCH', headers: AUTH_HEADERS, body: JSON.stringify({ pinned: val })
    })
    setConversations(prev => prev.map(c => c.id === id ? { ...c, pinned: val } : c))
  }

  const keepForeverConv = async (id: string, val: boolean) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, {
      method: 'PATCH', headers: AUTH_HEADERS, body: JSON.stringify({ keep_forever: val })
    })
    setConversations(prev => prev.map(c => c.id === id ? { ...c, keep_forever: val } : c))
  }

  const renameConv = async (id: string, title: string) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, {
      method: 'PATCH', headers: AUTH_HEADERS, body: JSON.stringify({ title })
    })
    setConversations(prev => prev.map(c => c.id === id ? { ...c, title } : c))
    if (activeConvId === id) setTitleValue(title)
  }

  const saveTitle = async () => {
    if (!activeConvId || !titleValue.trim()) return
    setEditingTitle(false)
    await renameConv(activeConvId, titleValue.trim())
  }

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      sendMessage()
    }
  }

  // ── Active conv info ──────────────────────────────────────────────────────
  const activeConv = conversations.find(c => c.id === activeConvId)
  const activePersona = personas.find(p => p.id === selectedPersonaId)

  return (
    <div className="flex h-full w-full overflow-hidden">

      {/* Identity wizard — first-run and /soul /identity /user commands */}
      {wizardMode && (
        <IdentityWizard
          mode={wizardMode}
          aiName={aiName}
          onComplete={(newAiName) => {
            if (newAiName) setAiName(newAiName)
            setWizardMode(null)
            setUserExists(true)
          }}
          onDismiss={wizardMode !== 'firstrun' ? () => setWizardMode(null) : undefined}
        />
      )}

      {/* Sidebar */}
      <Sidebar
        conversations={filteredConvs}
        activeId={activeConvId}
        onSelect={id => loadSession(id)}
        onNew={newChat}
        onDelete={deleteConv}
        onPin={pinConv}
        onKeepForever={keepForeverConv}
        onRename={renameConv}
        personas={personas}
        selectedPersonaId={selectedPersonaId}
        onPersonaChange={setSelectedPersonaId}
        models={models}
        selectedModelId={selectedModelId}
        onModelChange={setSelectedModelId}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(p => !p)}
        width={sidebarWidth}
        onWidthChange={setSidebarWidth}
      />

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 h-full">

        {/* Top bar */}
        <div className="flex items-center gap-3 px-4 py-3 bg-white/80 dark:bg-gray-900/80 backdrop-blur border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
          {/* Hamburger (mobile / collapsed) */}
          {sidebarCollapsed && (
            <button
              onClick={() => setSidebarCollapsed(false)}
              className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          )}

          {/* Title */}
          <div className="flex-1 min-w-0">
            {editingTitle ? (
              <form onSubmit={e => { e.preventDefault(); saveTitle() }} className="flex items-center gap-1.5">
                <input
                  autoFocus
                  value={titleValue}
                  onChange={e => setTitleValue(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Escape') setEditingTitle(false) }}
                  className="text-sm font-medium rounded border border-orange-400 px-2 py-0.5 dark:bg-gray-800 dark:text-white min-w-0 flex-1"
                />
                <button type="submit" className="flex-shrink-0 px-2 py-0.5 text-xs font-medium bg-orange-500 hover:bg-orange-600 text-white rounded">
                  Save
                </button>
                <button type="button" onClick={() => setEditingTitle(false)} className="flex-shrink-0 text-xs text-gray-400 hover:text-gray-600 px-1">✕</button>
              </form>
            ) : (
              <button
                onClick={() => { setEditingTitle(true); setTitleValue(activeConv?.title || '') }}
                className="text-sm font-semibold text-gray-900 dark:text-white truncate hover:text-orange-600 dark:hover:text-orange-400 transition-colors text-left"
              >
                {activeConv?.title || (messages.length > 0 ? 'Untitled conversation' : 'New conversation')}
              </button>
            )}
          </div>

          {/* Badges */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {activePersona && (
              <span className="text-xs bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 px-2 py-0.5 rounded-full">
                {activePersona.name}
              </span>
            )}
            {activeModelName && (
              <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded-full hidden sm:block">
                {activeModelName}
              </span>
            )}
            <VoiceModeToggle
              active={voiceModeActive}
              onToggle={() => setVoiceModeActive(p => !p)}
            />
            {activeConv?.keep_forever && (
              <span title="Kept forever" className="text-xs">♾️</span>
            )}
            {activeConvId && (
              <button
                title="Share this conversation"
                disabled={sharing}
                onClick={async () => {
                  setSharing(true)
                  try {
                    const res = await fetch(`${API_BASE}/v1/shares`, {
                      method: 'POST',
                      headers: AUTH_HEADERS,
                      body: JSON.stringify({
                        resource_type: 'conversation',
                        resource_id: activeConvId,
                        access_level: 'view',
                        expires_in_days: 7,
                      }),
                    })
                    if (!res.ok) throw new Error('Failed to create share link')
                    const share = await res.json()
                    const fullUrl = `${window.location.origin}/share/${share.token}`
                    setShareModal({ url: fullUrl, expires_at: share.expires_at })
                  } catch (e: any) {
                    addToast({ type: 'error', title: 'Share failed', message: e.message, autoClose: 4000 })
                  } finally {
                    setSharing(false)
                  }
                }}
                className="text-xs p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 hover:text-orange-600 transition-colors"
              >
                {sharing ? '…' : '🔗'}
              </button>
            )}
          </div>
        </div>

        {/* Session recovery banner */}
        {recoverySnapshot && (
          <div className="flex-shrink-0 mx-4 mt-3 p-3 rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
                  🔄 Previous session found — {recoverySnapshot.messageCount} messages
                </p>
                {recoverySnapshot.summary && (
                  <p className="text-xs text-amber-700 dark:text-amber-400 mt-1 line-clamp-2">
                    {recoverySnapshot.summary}
                  </p>
                )}
              </div>
              <button
                onClick={() => {
                  // Inject a system message summarising the last session
                  setMessages([{
                    id: `recovery-${Date.now()}`,
                    role: 'assistant',
                    content: `🔄 **Session resumed from snapshot**\n\nI found a previous session with ${recoverySnapshot.messageCount} messages. Here's a brief summary of where we left off:\n\n${recoverySnapshot.summary || '_No summary available._'}\n\nFeel free to continue from where we left off!`,
                    created_at: new Date().toISOString(),
                  }])
                  setRecoverySnapshot(null)
                }}
                className="flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-500 hover:bg-amber-600 text-white"
              >
                Resume
              </button>
              <button
                onClick={() => setRecoverySnapshot(null)}
                className="flex-shrink-0 text-amber-600 hover:text-amber-800 dark:text-amber-400 text-lg leading-none"
              >
                ×
              </button>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-5 space-y-5 min-h-0">
          {loadingMessages ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex gap-1.5">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-sm">
                <div className="text-4xl mb-3">⚡</div>
                <h2 className="text-lg font-semibold text-gray-800 dark:text-white mb-1">
                  {activePersona?.name || 'DevForgeAI'}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {activePersona?.description || 'Start a conversation below'}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-3">
                  Press <kbd className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs">Ctrl+Enter</kbd> to send
                </p>
              </div>
            </div>
          ) : (
            messages.map(msg => <MessageBubble key={msg.id} msg={msg} conversationId={activeConvId} />)
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Voice Mode bar */}
        <VoiceMode
          active={voiceModeActive}
          onToggle={() => setVoiceModeActive(false)}
          onTranscript={sendVoiceMessage}
          lastAssistantMessage={lastAssistantMessage}
          loading={loading}
          workflowTrigger={voiceWorkflowTrigger}
          activePipelineId={voicePipelineId}
        />

        {/* Input bar */}
        <div className="flex-shrink-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 px-4 pt-3 pb-4 rounded-b-xl">
          <div className="max-w-4xl mx-auto">
            <div className="flex gap-2 items-end relative">
              {/* Toggle: chat <-> image mode */}
              <button
                onClick={() => {
                  // Switching modes — move any already-typed text over so the
                  // user doesn't have to retype their prompt.
                  if (!showImageGen) {
                    // chat → image: carry chat draft into image prompt
                    if (input.trim() && !imagePrompt.trim()) {
                      setImagePrompt(input)
                      setInput('')
                    }
                  } else {
                    // image → chat: carry image draft into chat input
                    if (imagePrompt.trim() && !input.trim()) {
                      setInput(imagePrompt)
                      setImagePrompt('')
                    }
                  }
                  setShowImageGen(prev => !prev)
                }}
                title={showImageGen ? 'Switch to chat' : 'Generate an image'}
                className={`flex-shrink-0 p-2.5 rounded-xl border transition-colors ${
                  showImageGen
                    ? 'bg-purple-100 dark:bg-purple-900/30 border-purple-300 dark:border-purple-600 text-purple-600 dark:text-purple-400'
                    : 'border-gray-200 dark:border-gray-700 text-gray-400 hover:text-purple-500 hover:border-purple-300'
                }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  {showImageGen ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  )}
                </svg>
              </button>

              {showImageGen ? (
                /* Image generation dialog */
                <div className="flex-1 flex flex-col gap-2">
                  {/* Row 1: Provider + ComfyUI status */}
                  <div className="flex gap-2 items-center flex-wrap">
                    <select
                      value={imageProvider}
                      onChange={e => setImageProvider(e.target.value as any)}
                      className="text-xs rounded-lg border border-purple-200 dark:border-purple-700 dark:bg-gray-800 dark:text-gray-200 py-1.5 pl-2 pr-6 focus:ring-purple-400 focus:border-purple-400"
                    >
                      <option value="comfyui-local">ComfyUI (Local)</option>
                      <option value="gemini-imagen">Gemini (Cloud)</option>
                    </select>

                    {imageProvider === 'comfyui-local' && (
                      <>
                        {/* Workflow picker — only selection needed; everything
                            else (checkpoint, LoRA, size, negative prompt) is
                            baked into the saved workflow. Edit in ComfyUI to change. */}
                        <select
                          value={selectedWorkflowId}
                          onChange={e => setSelectedWorkflowId(e.target.value)}
                          className="text-xs rounded-lg border border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 py-1.5 pl-2 pr-6 focus:ring-purple-400 focus:border-purple-400 max-w-[240px]"
                          title="Saved ComfyUI workflow (edit in ComfyUI to change settings)"
                        >
                          {workflows.length === 0 ? (
                            <option value="sdxl-standard">SDXL Standard</option>
                          ) : (
                            workflows.map(w => (
                              <option key={w.id} value={w.id}>{w.name}</option>
                            ))
                          )}
                        </select>

                        {/* Status dot */}
                        <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
                          comfyStatus === 'online' ? 'bg-green-400' : comfyStatus === 'checking' ? 'bg-yellow-400 animate-pulse' : 'bg-red-400'
                        }`} title={`ComfyUI: ${comfyStatus}`} />
                      </>
                    )}
                  </div>

                  {/* Patience notice for local ComfyUI generation */}
                  {imageProvider === 'comfyui-local' && (
                    <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/40 text-xs text-purple-700 dark:text-purple-300">
                      <span className="flex-shrink-0 mt-0.5">⏳</span>
                      <span>
                        <strong>Heads up:</strong> Local generation runs on your GPU and can take 30 seconds to several minutes
                        (first use loads the model into VRAM). Gemini is faster for quick iterations — ComfyUI wins on control and privacy.
                      </span>
                    </div>
                  )}

                  {/* Row 2: Prompt + generate button */}
                  <div className="flex gap-2 items-end">
                    <textarea
                      ref={imagePromptRef}
                      value={imagePrompt}
                      onChange={e => setImagePrompt(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          generateImage()
                        }
                      }}
                      placeholder="Describe the image you want to create... (Shift+Enter for newline)"
                      disabled={generatingImage}
                      autoFocus
                      rows={1}
                      className="flex-1 resize-none rounded-xl border border-purple-200 dark:border-purple-700 dark:bg-gray-800 dark:text-white px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 focus:border-transparent disabled:opacity-50 leading-relaxed whitespace-pre-wrap break-words overflow-y-auto"
                      style={{ minHeight: '42px' }}
                    />
                    <button
                      onClick={() => generateImage()}
                      disabled={generatingImage || !imagePrompt.trim()}
                      className="flex-shrink-0 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-200 dark:disabled:bg-gray-700 text-white disabled:text-gray-400 rounded-xl font-medium text-sm transition-colors"
                    >
                      {generatingImage ? '...' : 'Generate'}
                    </button>
                  </div>
                </div>
              ) : (
                /* Chat mode input */
                <>
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Message... (Ctrl+Enter to send)"
                    disabled={loading}
                    rows={1}
                    className="flex-1 resize-none rounded-xl border border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-white px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent disabled:opacity-50 leading-relaxed whitespace-pre-wrap break-words overflow-y-auto"
                    style={{ minHeight: '42px' }}
                  />
                  <MicrophoneButton
                    onTranscript={(text) => setInput(prev => prev ? prev + ' ' + text : text)}
                    disabled={loading}
                  />
                  <button
                    onClick={() => sendMessage()}
                    disabled={loading || !input.trim()}
                    className="flex-shrink-0 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-200 dark:disabled:bg-gray-700 text-white disabled:text-gray-400 rounded-xl font-medium text-sm transition-colors"
                  >
                    {loading ? (
                      <div className="flex gap-1 items-center">
                        <div className="w-1.5 h-1.5 bg-white rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-1.5 h-1.5 bg-white rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-1.5 h-1.5 bg-white rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    ) : (
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                      </svg>
                    )}
                  </button>
                </>
              )}
            </div>
            <div className="flex justify-between items-center mt-2 px-1">
              <span className="text-xs text-gray-400">
                {showImageGen ? 'Image mode' : (input.length > 0 ? `${input.length} chars` : '')}
              </span>
              <span className="text-xs text-gray-400">
                {showImageGen ? 'Enter to generate' : 'Ctrl+Enter to send'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Share link modal */}
      {shareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setShareModal(null)}>
          <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">🔗 Share this conversation</h2>
              <button onClick={() => setShareModal(null)} className="text-gray-400 hover:text-gray-600 p-1">✕</button>
            </div>
            <div className="px-6 py-5 space-y-3">
              <p className="text-xs text-gray-500">
                Anyone with this link can view this conversation (read-only).
                {shareModal.expires_at && ` Expires ${new Date(shareModal.expires_at).toLocaleDateString()}.`}
              </p>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={shareModal.url}
                  onClick={e => (e.target as HTMLInputElement).select()}
                  className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-orange-400"
                />
                <button
                  onClick={async () => {
                    await navigator.clipboard.writeText(shareModal.url)
                    addToast({ type: 'success', title: 'Copied!', message: 'Share link copied to clipboard', autoClose: 2000 })
                  }}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white"
                >
                  Copy
                </button>
              </div>
            </div>
            <div className="px-6 py-3 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex justify-end">
              <button onClick={() => setShareModal(null)} className="px-4 py-1.5 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
