'use client'

import { useState, useEffect } from 'react'

const API_BASE = 'http://localhost:19000'
const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

interface TailscaleInfo {
  hostname: string
  tailscale_ip: string | null
  frontend_url: string
  backend_url?: string
  instructions?: Record<string, string>
}

interface TelegramStatus {
  configured: boolean
  bot_username?: string | null
  authorized_chats?: number[]
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }}
      className="text-xs px-2 py-1 rounded border border-gray-600 text-gray-400 hover:text-white hover:border-gray-400 transition-colors flex-shrink-0"
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  )
}

function Card({ icon, title, subtitle, children }: { icon: string; title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
        </div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

export function RemoteAccessTab() {
  const [tailscale, setTailscale] = useState<TailscaleInfo | null>(null)
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [backendStatus, setBackendStatus] = useState<{ running: boolean; healthy: boolean; pid: number | null } | null>(null)
  const [controlling, setControlling] = useState<string | null>(null)

  const [botToken, setBotToken] = useState('')
  const [chatIds, setChatIds] = useState('')
  const [testMsg, setTestMsg] = useState('Hello from DevForgeAI! 👋')
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null)

  const [saving, setSaving] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const fb = (type: 'ok' | 'err', text: string) => {
    setFeedback({ type, text })
    setTimeout(() => setFeedback(null), 4000)
  }

  const fetchBackendStatus = async () => {
    const res = await fetch('/api/backend').then(r => r.json()).catch(() => null)
    if (res) setBackendStatus(res)
  }

  const controlBackend = async (action: 'start' | 'stop' | 'restart') => {
    setControlling(action)
    try {
      const res = await fetch('/api/backend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      }).then(r => r.json())
      fb(res.ok ? 'ok' : 'err', res.message)
      await fetchBackendStatus()
      // If backend came back up, also refresh remote status
      if (res.ok && action !== 'stop') {
        setTimeout(async () => {
          const [ts, tg] = await Promise.all([
            fetch(`${API_BASE}/v1/remote/tailscale-info`, { headers: AUTH }).then(r => r.json()).catch(() => null),
            fetch(`${API_BASE}/v1/telegram/status`, { headers: AUTH }).then(r => r.json()).catch(() => null),
          ])
          if (ts) setTailscale(ts)
          if (tg) setTelegram(tg)
        }, 1000)
      }
    } catch (e: any) { fb('err', e.message) }
    finally { setControlling(null) }
  }

  useEffect(() => {
    fetchBackendStatus()
    Promise.all([
      fetch(`${API_BASE}/v1/remote/tailscale-info`, { headers: AUTH }).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/v1/telegram/status`, { headers: AUTH }).then(r => r.json()).catch(() => null),
    ]).then(([ts, tg]) => {
      setTailscale(ts)
      setTelegram(tg)
      if (tg?.authorized_chats?.length) setChatIds(tg.authorized_chats.join(', '))
      setLoading(false)
    })
    // Poll backend status every 10s
    const interval = setInterval(fetchBackendStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  const saveBotToken = async () => {
    if (!botToken.trim()) return
    setSaving('token')
    try {
      await fetch(`${API_BASE}/v1/api-keys/telegram_bot_token`, {
        method: 'PUT', headers: AUTH, body: JSON.stringify({ value: botToken.trim() })
      })
      setBotToken('')
      const res = await fetch(`${API_BASE}/v1/telegram/status`, { headers: AUTH }).then(r => r.json())
      setTelegram(res)
      fb('ok', 'Bot token saved — active immediately')
    } catch (e: any) { fb('err', e.message) }
    finally { setSaving(null) }
  }

  const saveChatIds = async () => {
    if (!chatIds.trim()) return
    setSaving('chats')
    try {
      await fetch(`${API_BASE}/v1/api-keys/telegram_chat_ids`, {
        method: 'PUT', headers: AUTH, body: JSON.stringify({ value: chatIds.trim() })
      })
      // Refresh status immediately so Send Test button activates
      const res = await fetch(`${API_BASE}/v1/telegram/status`, { headers: AUTH }).then(r => r.json()).catch(() => null)
      if (res) setTelegram(res)
      fb('ok', 'Chat IDs saved')
    } catch (e: any) { fb('err', e.message) }
    finally { setSaving(null) }
  }

  const registerWebhook = async () => {
    setSaving('webhook')
    try {
      const res = await fetch(`${API_BASE}/v1/telegram/register-webhook`, {
        method: 'POST', headers: AUTH, body: '{}'
      }).then(r => r.json())
      if (res.ok) { setWebhookUrl(res.webhook_url); fb('ok', 'Webhook registered with Telegram') }
      else fb('err', res.detail || 'Webhook registration failed')
    } catch (e: any) { fb('err', e.message) }
    finally { setSaving(null) }
  }

  const sendTest = async () => {
    if (!testMsg.trim() || !telegram?.authorized_chats?.length) return
    setSaving('test')
    try {
      const res = await fetch(`${API_BASE}/v1/telegram/send`, {
        method: 'POST', headers: AUTH,
        body: JSON.stringify({ chat_id: String(telegram.authorized_chats[0]), text: testMsg })
      }).then(r => r.json())
      if (res.result?.message_id || res.ok) fb('ok', 'Test message sent!')
      else fb('err', res.description || 'Send failed')
    } catch (e: any) { fb('err', e.message) }
    finally { setSaving(null) }
  }

  const FIREWALL_CMDS = [
    `netsh advfirewall firewall add rule name="DevForgeAI API (19000)" dir=in action=allow protocol=tcp localport=19000 remoteip=100.64.0.0/10`,
    `netsh advfirewall firewall add rule name="DevForgeAI Frontend (3001)" dir=in action=allow protocol=tcp localport=3001 remoteip=100.64.0.0/10`,
  ]

  const TELEGRAM_COMMANDS = [
    '/start or /help — show all commands',
    '/status — system health (CPU, memory, uptime)',
    '/sessions — active agent sessions',
    '/models — available models',
    '/run <agent> <task> — start an agent session',
    '/cancel <session_id> — cancel a session',
    '/continue — resume your last conversation',
    'Any text — chat with the default persona',
  ]

  if (loading) return <div className="text-sm text-gray-400 py-8 text-center">Loading remote settings...</div>

  return (
    <div className="space-y-5">
      {/* Feedback toast */}
      {feedback && (
        <div className={`px-4 py-2.5 rounded-lg text-sm border ${feedback.type === 'ok' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border-green-200 dark:border-green-700' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border-red-200 dark:border-red-700'}`}>
          {feedback.type === 'ok' ? '✓ ' : '✗ '}{feedback.text}
        </div>
      )}

      {/* Backend Control */}
      <Card icon="⚙️" title="Backend Process" subtitle="Start, stop or restart the Python backend (port 19000)">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                backendStatus?.healthy ? 'bg-green-500' :
                backendStatus?.running ? 'bg-yellow-400 animate-pulse' :
                'bg-red-500'
              }`} />
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {backendStatus?.healthy ? 'Running & healthy' :
                   backendStatus?.running ? 'Running (not responding)' :
                   backendStatus === null ? 'Checking...' :
                   'Stopped'}
                </p>
                {backendStatus?.pid && (
                  <p className="text-xs text-gray-400">PID {backendStatus.pid} · port {19000}</p>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              {!backendStatus?.running ? (
                <button onClick={() => controlBackend('start')} disabled={!!controlling}
                  className="px-3 py-1.5 text-xs font-medium bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-40 transition-colors">
                  {controlling === 'start' ? '...' : '▶ Start'}
                </button>
              ) : (
                <>
                  <button onClick={() => controlBackend('restart')} disabled={!!controlling}
                    className="px-3 py-1.5 text-xs font-medium bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-40 transition-colors">
                    {controlling === 'restart' ? '...' : '↺ Restart'}
                  </button>
                  <button onClick={() => controlBackend('stop')} disabled={!!controlling}
                    className="px-3 py-1.5 text-xs font-medium border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg disabled:opacity-40 transition-colors">
                    {controlling === 'stop' ? '...' : '■ Stop'}
                  </button>
                </>
              )}
              <button onClick={fetchBackendStatus} disabled={!!controlling}
                className="px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg disabled:opacity-40 transition-colors">
                ↻
              </button>
            </div>
          </div>
          {!backendStatus?.healthy && backendStatus?.running === false && (
            <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 px-3 py-2 rounded-lg">
              Backend is down — most app features won't work until it's restarted. Click ▶ Start above.
            </p>
          )}
        </div>
      </Card>

      {/* Remote / Tailscale status */}
      <Card icon="🌐" title="Remote Access Status" subtitle="Tailscale network configuration">
        {tailscale ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              {tailscale.tailscale_ip
                ? <span className="text-xs px-2.5 py-1 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 font-medium">✓ Tailscale connected</span>
                : <span className="text-xs px-2.5 py-1 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 font-medium">⚠ Local only</span>
              }
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                ['Hostname', tailscale.hostname],
                ['Tailscale IP', tailscale.tailscale_ip || 'Not connected'],
                ['Frontend', tailscale.frontend_url || `http://${tailscale.tailscale_ip || 'localhost'}:3001`],
                ['Backend', tailscale.backend_url || `http://${tailscale.tailscale_ip || 'localhost'}:19000`],
              ].map(([label, val]) => (
                <div key={label} className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                  <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">{label}</p>
                  <p className="text-sm font-mono text-gray-800 dark:text-gray-200 break-all">{val}</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400">Could not load remote status</p>
        )}
      </Card>

      {/* Telegram status */}
      <Card icon="🤖" title="Telegram Bot" subtitle="Chat with DevForgeAI from anywhere">
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {telegram?.configured
              ? <span className="text-xs px-2.5 py-1 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 font-medium">✓ Configured {telegram.bot_username ? `@${telegram.bot_username}` : ''}</span>
              : <span className="text-xs px-2.5 py-1 rounded-full bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400 font-medium">✗ Not configured</span>
            }
            {telegram?.authorized_chats && telegram.authorized_chats.length > 0 && (
              <span className="text-xs text-gray-400">{telegram.authorized_chats.length} authorized chat{telegram.authorized_chats.length > 1 ? 's' : ''}</span>
            )}
          </div>

          {/* Bot token */}
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              Bot Token <span className="text-gray-400 font-normal">— get from <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-orange-500 hover:underline">@BotFather</a></span>
            </label>
            <div className="flex gap-2">
              <input type="password" value={botToken} onChange={e => setBotToken(e.target.value)}
                placeholder={telegram?.configured ? '••••••••••••• (already set — paste new to update)' : 'Paste your bot token...'}
                className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400"
                onKeyDown={e => e.key === 'Enter' && saveBotToken()} />
              <button onClick={saveBotToken} disabled={!botToken.trim() || saving === 'token'}
                className="px-3 py-2 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-40 transition-colors">
                {saving === 'token' ? '...' : 'Save'}
              </button>
            </div>
          </div>

          {/* Chat IDs */}
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              Authorized Chat IDs <span className="text-gray-400 font-normal">— get yours from <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer" className="text-orange-500 hover:underline">@userinfobot</a></span>
            </label>
            <div className="flex gap-2">
              <input value={chatIds} onChange={e => setChatIds(e.target.value)}
                placeholder="123456789, -100987654321"
                className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400"
                onKeyDown={e => e.key === 'Enter' && saveChatIds()} />
              <button onClick={saveChatIds} disabled={!chatIds.trim() || saving === 'chats'}
                className="px-3 py-2 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-40 transition-colors">
                {saving === 'chats' ? '...' : 'Save'}
              </button>
            </div>
          </div>

          {/* Polling status */}
          <div className="pt-3 border-t border-gray-100 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-gray-700 dark:text-gray-300">Receive Mode</p>
                <p className="text-xs text-gray-400">Polling — backend checks Telegram every 2s for new messages</p>
              </div>
              {telegram?.configured && (
                <span className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                  Active
                </span>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Test message */}
      <Card icon="📨" title="Quick Test" subtitle="Send a test message to verify everything works">
        <div className="flex gap-2">
          <input value={testMsg} onChange={e => setTestMsg(e.target.value)}
            placeholder="Test message..."
            className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            onKeyDown={e => e.key === 'Enter' && sendTest()} />
          <button onClick={sendTest}
            disabled={!telegram?.configured || !telegram.authorized_chats?.length || !testMsg.trim() || saving === 'test'}
            className="px-4 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-40 transition-colors">
            {saving === 'test' ? '...' : 'Send'}
          </button>
        </div>
        {telegram?.configured && !telegram.authorized_chats?.length && (
          <p className="text-xs text-amber-600 mt-2">⚠ Add authorized chat IDs above before testing</p>
        )}
      </Card>

      {/* Bot commands reference */}
      <Card icon="💬" title="Bot Commands" subtitle="What you can do from Telegram">
        <div className="space-y-1.5">
          {TELEGRAM_COMMANDS.map((cmd, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <span className="text-orange-500 font-mono text-xs mt-0.5 flex-shrink-0">›</span>
              <span className="text-gray-600 dark:text-gray-300">{cmd}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-700 text-xs text-blue-700 dark:text-blue-300">
          <strong>Context is kept</strong> — your Telegram conversations remember history per chat ID. Use <code>/continue</code> to resume where you left off after a restart.
        </div>
      </Card>

      {/* Firewall rules */}
      <Card icon="🔒" title="Firewall Rules" subtitle="Run as Administrator to allow Tailscale access">
        <div className="space-y-3">
          {FIREWALL_CMDS.map((cmd, i) => (
            <div key={i}>
              <p className="text-xs text-gray-500 mb-1">Port {i === 0 ? '19000 (Backend API)' : '3001 (Frontend)'}</p>
              <div className="flex items-center gap-2 bg-gray-900 rounded-lg px-3 py-2.5">
                <code className="text-xs font-mono text-green-400 flex-1 break-all">{cmd}</code>
                <CopyButton text={cmd} />
              </div>
            </div>
          ))}
          <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg px-3 py-2">
            ⚠ These restrict access to Tailscale IP range only (100.64.0.0/10). Your data stays private.
          </p>
        </div>
      </Card>
    </div>
  )
}
