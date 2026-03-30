'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

// ─── Minimal markdown renderer (no external dep) ────────────────────────────
function renderMarkdown(md: string): string {
  return md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Fenced code blocks
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre class="bg-gray-900 text-green-400 rounded-xl p-4 my-3 overflow-x-auto text-sm font-mono leading-relaxed"><code>${code.trim()}</code></pre>`)
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 dark:bg-gray-800 text-orange-600 dark:text-orange-400 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold">$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // H1
    .replace(/^# (.+)$/gm, '<h1 class="text-3xl font-bold text-gray-900 dark:text-white mt-8 mb-4 pb-3 border-b border-gray-200 dark:border-gray-700">$1</h1>')
    // H2
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-bold text-gray-900 dark:text-white mt-8 mb-3 flex items-center gap-2"><span class="w-1 h-5 bg-orange-500 rounded-full inline-block"></span>$1</h2>')
    // H3
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-gray-800 dark:text-gray-200 mt-5 mb-2">$1</h3>')
    // H4
    .replace(/^#### (.+)$/gm, '<h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mt-4 mb-1 uppercase tracking-wide">$1</h4>')
    // Horizontal rule
    .replace(/^---$/gm, '<hr class="my-6 border-gray-200 dark:border-gray-700"/>')
    // Tables
    .replace(/^\|(.+)\|$/gm, (line) => {
      const cells = line.split('|').slice(1, -1).map(c => c.trim())
      return `<tr>${cells.map(c => `<td class="px-3 py-2 border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-300">${c}</td>`).join('')}</tr>`
    })
    .replace(/(<tr>.*<\/tr>\n?)+/gs, s => {
      const rows = s.trim().split('\n')
      // Make first row a header
      const header = rows[0].replace(/<td/g, '<th class="px-3 py-2 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm font-semibold text-gray-700 dark:text-gray-200 text-left"').replace(/<\/td>/g, '</th>')
      const body = rows.slice(2).filter(r => !r.match(/^\|[-: |]+\|$/)).join('\n')
      return `<div class="overflow-x-auto my-4"><table class="w-full border-collapse rounded-lg overflow-hidden">${header}${body}</table></div>`
    })
    // Remove table separator rows (|---|---|)
    .replace(/<tr><td[^>]*>-+<\/td>.*?<\/tr>\n?/g, '')
    // Unordered lists
    .replace(/^[*\-] (.+)$/gm, '<li class="flex gap-2 items-start"><span class="text-orange-500 mt-1.5 flex-shrink-0">•</span><span>$1</span></li>')
    .replace(/(<li class="flex[^>]*>.*?<\/li>\n?)+/gs, s => `<ul class="my-2 space-y-1">${s}</ul>`)
    // Numbered lists
    .replace(/^(\d+)\. (.+)$/gm, '<li class="flex gap-2 items-start"><span class="text-orange-500 font-mono text-sm mt-0.5 flex-shrink-0 w-5">$1.</span><span>$2</span></li>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer" class="text-orange-500 hover:text-orange-600 underline">$1</a>')
    // Paragraphs
    .replace(/^(?!<[hpultodc])(.+)$/gm, '<p class="text-gray-600 dark:text-gray-300 leading-relaxed my-1.5">$1</p>')
    // Clean up empty paragraphs
    .replace(/<p[^>]*>\s*<\/p>/g, '')
}

// ─── Table of contents parser ────────────────────────────────────────────────
function parseToc(md: string): Array<{ level: number; text: string; id: string }> {
  const headings: Array<{ level: number; text: string; id: string }> = []
  const lines = md.split('\n')
  for (const line of lines) {
    const m2 = line.match(/^## (.+)$/)
    const m3 = line.match(/^### (.+)$/)
    if (m2) {
      const text = m2[1]
      headings.push({ level: 2, text, id: text.toLowerCase().replace(/[^a-z0-9]+/g, '-') })
    } else if (m3) {
      const text = m3[1]
      headings.push({ level: 3, text, id: text.toLowerCase().replace(/[^a-z0-9]+/g, '-') })
    }
  }
  return headings
}

export default function HelpPage() {
  const [markdown, setMarkdown] = useState('')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [tocOpen, setTocOpen] = useState(true)

  useEffect(() => {
    fetch('/api/readme')
      .then(r => r.json())
      .then(d => { setMarkdown(d.content || ''); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const toc = parseToc(markdown)

  const filteredMarkdown = search.trim()
    ? markdown.split('\n').filter(line =>
        line.toLowerCase().includes(search.toLowerCase())
      ).join('\n')
    : markdown

  const html = renderMarkdown(filteredMarkdown)

  if (loading) return (
    <div className="flex justify-center py-16">
      <div className="flex gap-1.5">{[0,1,2].map(i => (
        <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />
      ))}</div>
    </div>
  )

  return (
    <div className="flex gap-8 max-w-6xl">
      {/* Table of contents — sticky sidebar */}
      <aside className={`hidden lg:block flex-shrink-0 ${tocOpen ? 'w-56' : 'w-8'} transition-all`}>
        <div className="sticky top-0 pt-1">
          <div className="flex items-center justify-between mb-3">
            {tocOpen && <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Contents</p>}
            <button onClick={() => setTocOpen(t => !t)}
              className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 transition-colors ml-auto">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                {tocOpen
                  ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
                  : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M6 5l7 7-7 7" />
                }
              </svg>
            </button>
          </div>
          {tocOpen && (
            <nav className="space-y-0.5 max-h-[80vh] overflow-y-auto pr-2">
              {toc.map((item, i) => (
                <a key={i} href={`#${item.id}`}
                  className={`block text-xs leading-relaxed rounded px-2 py-1 transition-colors hover:bg-orange-50 dark:hover:bg-orange-900/20 hover:text-orange-600 dark:hover:text-orange-400 text-gray-500 dark:text-gray-400 ${
                    item.level === 3 ? 'pl-4' : 'font-medium'
                  }`}>
                  {item.text}
                </a>
              ))}
            </nav>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Help & Documentation</h1>
            <p className="text-sm text-gray-500 mt-1">Everything you need to know about DevForgeAI</p>
          </div>
          <div className="flex gap-2 flex-shrink-0">
            <Link href="/chat"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors">
              💬 Start Chatting
            </Link>
          </div>
        </div>

        {/* Quick links */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          {[
            { icon: '⚡', label: 'Quick Start', href: '#quick-start' },
            { icon: '💬', label: 'Chat', href: '#chat' },
            { icon: '🤖', label: 'Agents', href: '#agents' },
            { icon: '🌐', label: 'Remote Access', href: '#remote-access-tailscale' },
          ].map(item => (
            <a key={item.label} href={item.href}
              className="flex items-center gap-2 px-3 py-2.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl hover:border-orange-300 hover:shadow-sm transition-all text-sm font-medium text-gray-700 dark:text-gray-300">
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </a>
          ))}
        </div>

        {/* Search */}
        <div className="relative mb-6">
          <svg className="absolute left-3 top-2.5 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search documentation..."
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent"
          />
          {search && (
            <button onClick={() => setSearch('')}
              className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600 text-xs">✕</button>
          )}
        </div>

        {/* Rendered README */}
        <div
          className="prose-like bg-white dark:bg-gray-800/50 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 sm:p-8"
          dangerouslySetInnerHTML={{ __html: html }}
        />

        {/* Footer */}
        <div className="mt-8 flex items-center justify-between text-xs text-gray-400 pb-4">
          <span>DevForgeAI Documentation · Rendered from README.md</span>
          <a href="https://github.com/chriskesler35/model_mesh" target="_blank" rel="noreferrer"
            className="hover:text-orange-500 transition-colors">
            View on GitHub →
          </a>
        </div>
      </div>
    </div>
  )
}
