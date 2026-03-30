'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useToast } from '../ToastProvider'

// ─── Constants ────────────────────────────────────────────────────────────────
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:19000'
const API_KEY = 'modelmesh_local_dev_key'
const AUTH = { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' }

// ─── Types ────────────────────────────────────────────────────────────────────
interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  model?: string
  created_at: string
  streaming?: boolean
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
  for (const c of convs) {
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
  personas, selectedPersonaId, onPersonaChange, searchQuery, onSearchChange, collapsed, onToggle
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
  searchQuery: string
  onSearchChange: (q: string) => void
  collapsed: boolean
  onToggle: () => void
}) {
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
      <aside className={`
        fixed lg:relative inset-y-0 left-0 z-30 lg:z-auto
        flex flex-col bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700
        transition-all duration-200 ease-in-out
        ${collapsed ? '-translate-x-full lg:translate-x-0 lg:w-0 lg:overflow-hidden lg:border-0' : 'translate-x-0 w-72'}
      `}>
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

        {/* New chat */}
        <div className="px-3 py-3">
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

        {/* Persona selector */}
        <div className="px-3 pb-2">
          <select
            value={selectedPersonaId}
            onChange={e => onPersonaChange(e.target.value)}
            className="w-full text-xs rounded-md border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 py-1.5 pl-2 pr-6 focus:ring-orange-500 focus:border-orange-400"
          >
            {personas.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
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

        {/* Footer */}
        <div className="px-3 py-2 border-t border-gray-100 dark:border-gray-800">
          <Link href="/" className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            ← Back to dashboard
          </Link>
        </div>
      </aside>
    </>
  )
}

// ─── Message bubble ───────────────────────────────────────────────────────────
function MessageBubble({ msg }: { msg: Message }) {
  const [copied, setCopied] = useState(false)
  const isUser = msg.role === 'user'

  const copy = () => {
    navigator.clipboard.writeText(msg.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
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
        </div>
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

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ChatPage() {
  const searchParams = useSearchParams()
  const router = useRouter()

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])
  const [selectedPersonaId, setSelectedPersonaId] = useState('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchDebounce, setSearchDebounce] = useState('')
  const [activeModelName, setActiveModelName] = useState<string>('')
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleValue, setTitleValue] = useState('')
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [userExists, setUserExists] = useState(true)   // assume true until checked
  const [aiName, setAiName] = useState('Aria')

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
        router.replace('/chat', { scroll: false })
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
            method: 'PATCH', headers: AUTH, body: JSON.stringify({ pinned: true })
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
          setImagePrompt(arg)
          setShowImageGen(true)
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
        if (arg) {
          await fetch('http://localhost:19000/v1/methods/activate', {
            method: 'POST', headers: AUTH, body: JSON.stringify({ method_id: arg.toLowerCase() })
          })
          const methodMeta: Record<string, { icon: string; color: string }> = {
            bmad: { icon: 'BMAD', color: 'purple' }, gsd: { icon: 'GSD', color: 'orange' },
            superpowers: { icon: 'SP', color: 'blue' }, gtrack: { icon: 'GT', color: 'green' },
            standard: { icon: 'STD', color: 'gray' }
          }
          const m = methodMeta[arg.toLowerCase()]
          if (m) {
            setActiveMethod(arg.toLowerCase() === 'standard' ? null : { id: arg.toLowerCase(), name: arg, icon: m.icon, color: m.color })
            addToast({ type: 'success', title: 'Method switched', message: arg + ' mode active', autoClose: 2000 })
          } else {
            addToast({ type: 'error', title: 'Unknown method', message: 'Try: bmad, gsd, superpowers, gtrack, standard', autoClose: 3000 })
          }
        } else {
          window.location.href = '/methods'
        }
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
  }, [activeConvId, messages, personas, addToast, setUserExists, router])

  const [showImageGen, setShowImageGen] = useState(false)
  const [imagePrompt, setImagePrompt] = useState('')
  const [generatingImage, setGeneratingImage] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const init = async () => {
      try {
        const [personasRes, convsRes, identityRes] = await Promise.all([
          fetch(`${API_BASE}/v1/personas`, { headers: AUTH }).then(r => r.json()),
          fetch(`${API_BASE}/v1/conversations?limit=100&pinned_first=true`, { headers: AUTH }).then(r => r.json()),
          fetch(`${API_BASE}/v1/identity/status`, { headers: AUTH }).then(r => r.json()),
        ])

        const ps: Persona[] = personasRes.data || []
        setPersonas(ps)

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
          if (sessionParam && convs.find(c => c.id === sessionParam)) {
            loadSession(sessionParam, convs)
          } else {
            const lastId = localStorage.getItem('devforge_last_session')
            if (lastId && convs.find(c => c.id === lastId)) {
              loadSession(lastId, convs)
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
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 144) + 'px'
    }
  }, [input])

  // ── Load session ──────────────────────────────────────────────────────────
  const loadSession = useCallback(async (id: string, convList?: Conversation[]) => {
    setActiveConvId(id)
    setLoadingMessages(true)
    localStorage.setItem('devforge_last_session', id)
    router.replace(`/chat?session=${id}`, { scroll: false })

    // Update title input
    const conv = (convList || conversations).find(c => c.id === id)
    setTitleValue(conv?.title || '')

    try {
      const res = await fetch(`${API_BASE}/v1/conversations/${id}/messages?limit=200`, { headers: AUTH })
      const data = await res.json()
      const msgs: Message[] = (data.data || []).map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        created_at: m.created_at,
      }))
      setMessages(msgs)
    } catch (e) {
      console.error('Failed to load messages:', e)
      setMessages([])
    } finally {
      setLoadingMessages(false)
    }
  }, [conversations, router])

  // ── New chat ──────────────────────────────────────────────────────────────
  const newChat = () => {
    setActiveConvId(null)
    setMessages([])
    setTitleValue('')
    router.replace('/chat', { scroll: false })
    localStorage.removeItem('devforge_last_session')
    textareaRef.current?.focus()
  }

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const text = input.trim()
    setInput('')

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
      }
      if (activeConvId) body.conversation_id = activeConvId

      const res = await fetch(`${API_BASE}/v1/chat/completions`, {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify(body),
      })

      const data = await res.json()

      if (!res.ok) {
        throw new Error(data?.detail?.error?.message || data?.detail || `Request failed (${res.status})`)
      }

      const fullContent = data.choices?.[0]?.message?.content || ''
      const modelName = data.model || ''
      const convId = data.conversation_id || data.modelmesh?.conversation_id || activeConvId

      // Update assistant message
      setMessages(prev => prev.map(m =>
        m.id === assistantId
          ? { ...m, content: fullContent || '(no response)', streaming: false, model: modelName }
          : m
      ))
      setActiveModelName(modelName)

      // Update conversation state
      if (convId && convId !== activeConvId) {
        setActiveConvId(convId)
        localStorage.setItem('devforge_last_session', convId)
        router.replace(`/chat?session=${convId}`, { scroll: false })
        refreshConversations()
      } else if (convId) {
        setConversations(prev => prev.map(c =>
          c.id === convId ? { ...c, last_message_at: new Date().toISOString(), message_count: (c.message_count || 0) + 2 } : c
        ))
        const conv = conversations.find(c => c.id === convId)
        if (conv && !conv.title && messages.length === 0) {
          const autoTitle = text.slice(0, 60) + (text.length > 60 ? '...' : '')
          setTitleValue(autoTitle)
          setConversations(prev => prev.map(c => c.id === convId ? { ...c, title: autoTitle } : c))
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

  const generateImage = async () => {
    const prompt = imagePrompt.trim()
    if (!prompt || generatingImage) return
    setGeneratingImage(true)
    setShowImageGen(false)
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
      content: '🎨 Image generation submitted — you\'ll get a notification when it\'s ready!',
      streaming: false,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg, assistantMsg])

    // Save to conversation — post image request as a real chat message so it persists
    try {
      let convId = activeConvId
      const defaultPersonaId = personas.find((p: any) => p.is_default)?.id || selectedPersonaId
      try {
        const saveBody: any = {
          model: defaultPersonaId,
          messages: [{ role: 'user', content: `🖼️ Generate image: ${prompt}` }],
          stream: false,
        }
        if (convId) saveBody.conversation_id = convId
        const saveRes = await fetch(`${API_BASE}/v1/chat/completions`, {
          method: 'POST', headers: AUTH, body: JSON.stringify(saveBody)
        }).then(r => r.json())
        const newConvId = saveRes.conversation_id || saveRes.modelmesh?.conversation_id || null
        if (newConvId && newConvId !== convId) {
          convId = newConvId
          setActiveConvId(convId)
          localStorage.setItem('devforge_last_session', convId)
          router.replace(`/chat?session=${convId}`, { scroll: false })
        }
        // Update sidebar title to reflect image request
        if (convId) {
          const autoTitle = `🖼️ ${prompt.slice(0, 50)}${prompt.length > 50 ? '...' : ''}`
          await fetch(`${API_BASE}/v1/conversations/${convId}`, {
            method: 'PATCH', headers: AUTH, body: JSON.stringify({ title: autoTitle })
          }).catch(() => {})
          setConversations(prev => prev.map(c =>
            c.id === convId ? { ...c, title: autoTitle, last_message_at: new Date().toISOString() } : c
          ))
          setTitleValue(autoTitle)
        }
        refreshConversations()
      } catch { /* non-fatal - image still generates */ }

      await submitTask('image_gen', {
        prompt,
        model: 'comfyui-local',
        size: '1024x1024',
        format: 'png',
      }, convId || undefined)
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
      const res = await fetch(`${API_BASE}/v1/conversations?limit=100&pinned_first=true`, { headers: AUTH })
      const data = await res.json()
      setConversations(data.data || [])
    } catch { /* silent */ }
  }

  // ── Conversation actions ──────────────────────────────────────────────────
  const deleteConv = async (id: string) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, { method: 'DELETE', headers: AUTH })
    setConversations(prev => prev.filter(c => c.id !== id))
    if (activeConvId === id) newChat()
  }

  const pinConv = async (id: string, val: boolean) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, {
      method: 'PATCH', headers: AUTH, body: JSON.stringify({ pinned: val })
    })
    setConversations(prev => prev.map(c => c.id === id ? { ...c, pinned: val } : c))
  }

  const keepForeverConv = async (id: string, val: boolean) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, {
      method: 'PATCH', headers: AUTH, body: JSON.stringify({ keep_forever: val })
    })
    setConversations(prev => prev.map(c => c.id === id ? { ...c, keep_forever: val } : c))
  }

  const renameConv = async (id: string, title: string) => {
    await fetch(`${API_BASE}/v1/conversations/${id}`, {
      method: 'PATCH', headers: AUTH, body: JSON.stringify({ title })
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
    <div className="flex h-full w-full overflow-hidden rounded-xl">

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
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(p => !p)}
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
            {activeConv?.keep_forever && (
              <span title="Kept forever" className="text-xs">♾️</span>
            )}
          </div>
        </div>

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
            messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div className="flex-shrink-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 px-4 pt-3 pb-4 rounded-b-xl">
          <div className="flex gap-2 items-end max-w-4xl mx-auto relative">
            {/* Toggle: chat ↔ image mode */}
            <button
              onClick={() => setShowImageGen(prev => !prev)}
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
              /* Image mode input */
              <>
                <input
                  type="text"
                  value={imagePrompt}
                  onChange={e => setImagePrompt(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && generateImage()}
                  placeholder="Describe the image you want to create…"
                  disabled={generatingImage}
                  autoFocus
                  className="flex-1 rounded-xl border border-purple-200 dark:border-purple-700 dark:bg-gray-800 dark:text-white px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 focus:border-transparent disabled:opacity-50"
                />
                <button
                  onClick={generateImage}
                  disabled={generatingImage || !imagePrompt.trim()}
                  className="flex-shrink-0 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-200 dark:disabled:bg-gray-700 text-white disabled:text-gray-400 rounded-xl font-medium text-sm transition-colors"
                >
                  {generatingImage ? '…' : '🖼️'}
                </button>
              </>
            ) : (
              /* Chat mode input */
              <>
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Message… (Ctrl+Enter to send)"
                  disabled={loading}
                  rows={1}
                  className="flex-1 resize-none rounded-xl border border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-white px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent disabled:opacity-50 leading-relaxed"
                  style={{ minHeight: '42px', maxHeight: '144px' }}
                />
                <button
                  onClick={sendMessage}
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
          <div className="flex justify-between items-center mt-2 max-w-4xl mx-auto px-1">
            <span className="text-xs text-gray-400">
              {showImageGen ? 'Image mode — click 💬 to switch back' : (input.length > 0 ? `${input.length} chars` : '')}
            </span>
            <span className="text-xs text-gray-400">
              {showImageGen ? 'Enter to generate' : 'Ctrl+Enter to send'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
