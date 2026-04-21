'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'

const NAV_ITEMS = [
  { href: '/',                label: 'Dashboard',  icon: '◈' },
  { href: '/chat',            label: 'Chat',        icon: '💬' },
  { href: '/agents',          label: 'Agents',      icon: '🤖' },
  { href: '/agents/sessions', label: 'Agent Sessions', icon: '▶' },
  { href: '/workbench',       label: 'Workbench',   icon: '🔨' },
  { href: '/projects',        label: 'Projects',    icon: '🗂️' },
  { href: '/gallery',         label: 'Gallery',     icon: '🖼️' },
  { href: '/methods',         label: 'Methods',     icon: '🧠' },
  { href: '/marketplace',     label: 'Marketplace', icon: '🛍️' },
  { href: '/collaborate',     label: 'Collaborate', icon: '👥' },
  { href: '/personas',        label: 'Personas',    icon: '🎭' },
  { href: '/models',          label: 'Models',      icon: '⚡' },
  { href: '/stats',           label: 'Stats',       icon: '📊' },
  { href: '/settings',        label: 'Settings',    icon: '⚙️' },
  { href: '/help',            label: 'Help',         icon: '❓' },
]

const GROUPS = [
  { label: 'MAIN',   items: ['/', '/chat'] },
  { label: 'BUILD',  items: ['/agents', '/personas', '/projects', '/workbench', '/agents/sessions'] },
  { label: 'CREATE', items: ['/gallery', '/methods', '/marketplace'] },
  { label: 'MANAGE', items: ['/collaborate', '/models', '/stats', '/settings', '/help'] },
]

// Routes that should render indented under their parent
const NESTED_UNDER: Record<string, string> = {
  '/personas': '/agents',
  '/workbench': '/projects',
  '/agents/sessions': '/projects',
}

function ThemeToggle({ collapsed }: { collapsed: boolean }) {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem('theme')
    if (stored === 'dark' || (!stored && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      setIsDark(true)
      document.documentElement.classList.add('dark')
    }
  }, [])

  const toggle = () => {
    const next = !isDark
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
    setIsDark(next)
  }

  return (
    <button onClick={toggle} title={isDark ? 'Light mode' : 'Dark mode'}
      className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
      <span className="text-base flex-shrink-0">{isDark ? '☀️' : '🌙'}</span>
      {!collapsed && <span className="text-sm">{isDark ? 'Light mode' : 'Dark mode'}</span>}
    </button>
  )
}

interface CurrentUser {
  id: string
  username: string
  display_name: string
  role: string
  auth_method: string
  avatar_url?: string
}

function UserMenu({ collapsed }: { collapsed: boolean }) {
  const { user, logout } = useAuth()

  const handleLogout = async () => {
    await logout()
    window.location.href = '/auth/login'
  }

  const goToLogin = () => { window.location.href = '/auth/login' }

  if (!user) return null

  const isOwner = user.auth_method === 'master_key'
  const initial = (user.display_name || user.username || '?').charAt(0).toUpperCase()

  return (
    <div
      title={collapsed ? `${user.display_name} (${user.role})` : undefined}
      className="flex items-center gap-2 w-full px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
    >
      {user.avatar_url ? (
        <img src={user.avatar_url} alt="" className="w-6 h-6 rounded-full flex-shrink-0" />
      ) : (
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-orange-400 to-red-500 flex items-center justify-center text-white font-bold text-xs flex-shrink-0">
          {initial}
        </div>
      )}
      {!collapsed && (
        <>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">{user.display_name}</p>
            <p className="text-[10px] text-gray-400 truncate">{isOwner ? 'owner (master key)' : user.role}</p>
          </div>
          {isOwner ? (
            <button onClick={goToLogin}
              title="Sign in as a user"
              className="text-[10px] text-indigo-500 hover:text-indigo-700">Sign in</button>
          ) : (
            <button onClick={handleLogout}
              title="Sign out"
              className="text-[10px] text-gray-400 hover:text-red-500">⎋</button>
          )}
        </>
      )}
    </div>
  )
}

export default function Navigation() {
  const pathname = usePathname()
  const router = useRouter()

  // All hooks must be declared before any conditional returns
  const [mounted, setMounted] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [backendUp, setBackendUp] = useState<boolean | null>(null)

  useEffect(() => {
    setMounted(true)
    const stored = localStorage.getItem('sidebar-collapsed')
    if (stored === 'true') setCollapsed(true)
  }, [])

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch('/api/backend')
        const data = await res.json()
        setBackendUp(data.healthy)
      } catch {
        setBackendUp(false)
      }
    }
    check()
    const interval = setInterval(check, 15000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    for (const item of NAV_ITEMS) {
      router.prefetch(item.href)
    }
  }, [router])

  const toggle = () => {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem('sidebar-collapsed', String(next))
  }

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/'
    return pathname === href || pathname.startsWith(href + '/')
  }

  // Early return AFTER all hooks
  if (!mounted) {
    return <aside className="w-56 flex-shrink-0 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800" />
  }

  return (
    <aside className={`
      flex-shrink-0 flex flex-col h-full
      bg-white dark:bg-gray-900
      border-r border-gray-200 dark:border-gray-800
      transition-all duration-200 ease-in-out
      ${collapsed ? 'w-[60px]' : 'w-56'}
    `}>
      {/* Logo + collapse button */}
      <div className={`flex items-center h-14 border-b border-gray-100 dark:border-gray-800 flex-shrink-0 ${collapsed ? 'justify-center px-0' : 'justify-between px-4'}`}>
        {!collapsed && (
          <Link href="/" className="flex items-center gap-2 min-w-0">
            <img src="/favicon.svg" alt="" className="w-6 h-6 flex-shrink-0" />
            <span className="text-sm font-bold bg-gradient-to-r from-orange-500 to-red-500 bg-clip-text text-transparent truncate">
              DevForgeAI
            </span>
          </Link>
        )}
        <button onClick={toggle}
          className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors flex-shrink-0"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            {collapsed
              ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            }
          </svg>
        </button>
      </div>

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
        {GROUPS.map(group => {
          // Use group.items order (NOT NAV_ITEMS order) so nesting renders
          // immediately after the parent — e.g. /workbench right after /projects.
          const byHref = new Map(NAV_ITEMS.map(item => [item.href, item]))
          const groupItems = group.items.map(href => byHref.get(href)).filter((x): x is typeof NAV_ITEMS[number] => !!x)
          return (
            <div key={group.label}>
              {!collapsed && (
                <p className="px-2 mb-1 text-[10px] font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-widest">
                  {group.label}
                </p>
              )}
              <div className="space-y-0.5">
                {groupItems.map(item => {
                  const active = isActive(item.href)
                  const parentHref = NESTED_UNDER[item.href]
                  const isNested = !!parentHref && !collapsed
                  return (
                    <Link key={item.href} href={item.href}
                      title={collapsed ? item.label : undefined}
                      className={`
                        flex items-center gap-2.5 rounded-lg transition-colors
                        ${collapsed ? 'justify-center px-0 py-2.5' : isNested ? 'pl-7 pr-3 py-1.5' : 'px-3 py-2'}
                        ${active
                          ? 'bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400'
                          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-200'
                        }
                      `}>
                      <span className={`${isNested ? 'text-sm' : 'text-base'} flex-shrink-0 ${active ? '' : 'opacity-80'}`}>
                        {isNested ? '↳' : item.icon}
                      </span>
                      {!collapsed && (
                        <span className={`${isNested ? 'text-xs' : 'text-sm'} truncate ${active ? 'font-semibold' : 'font-medium'} flex items-center gap-1.5`}>
                          {isNested && <span className="text-xs opacity-70">{item.icon}</span>}
                          {item.label}
                        </span>
                      )}
                      {!collapsed && active && (
                        <span className="ml-auto w-1.5 h-1.5 rounded-full bg-orange-500 flex-shrink-0" />
                      )}
                    </Link>
                  )
                })}
              </div>
            </div>
          )
        })}
      </nav>

      {/* Bottom — backend status + theme toggle */}
      <div className="flex-shrink-0 border-t border-gray-100 dark:border-gray-800 p-2 space-y-1">
        <Link href="/settings"
          title={collapsed ? `Backend ${backendUp ? 'online' : backendUp === false ? 'offline' : 'checking'}` : undefined}
          className={`flex items-center gap-2.5 w-full px-3 py-2 rounded-lg transition-colors ${
            backendUp === false
              ? 'bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30'
              : 'hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}>
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
            backendUp === true  ? 'bg-green-500' :
            backendUp === false ? 'bg-red-500 animate-pulse' :
            'bg-gray-300 animate-pulse'
          }`} />
          {!collapsed && (
            <span className={`text-xs font-medium ${
              backendUp === false ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'
            }`}>
              {backendUp === true  ? 'Backend online' :
               backendUp === false ? 'Backend offline ⚡' :
               'Checking...'}
            </span>
          )}
        </Link>
        <UserMenu collapsed={collapsed} />
        <ThemeToggle collapsed={collapsed} />
      </div>
    </aside>
  )
}
