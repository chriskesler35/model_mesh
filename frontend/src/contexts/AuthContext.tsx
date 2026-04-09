'use client'

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getApiBase, TOKEN_KEY } from '@/lib/config'

export interface AuthUser {
  id: string
  username: string
  display_name: string
  role: string
  email?: string
  avatar_url?: string
  auth_method?: string
}

interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const USER_STORAGE_KEY = 'devforge_user'

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setUser(null)
      setIsLoading(false)
      return
    }

    try {
      const res = await fetch(`${getApiBase()}/v1/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setUser(data)
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(data))
      } else {
        // Token invalid — clear it
        localStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(USER_STORAGE_KEY)
        setUser(null)
      }
    } catch {
      // Network error — try cached user
      const cached = localStorage.getItem(USER_STORAGE_KEY)
      if (cached) {
        try { setUser(JSON.parse(cached)) } catch { setUser(null) }
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    // Load cached user immediately for fast render
    const cached = localStorage.getItem(USER_STORAGE_KEY)
    if (cached) {
      try { setUser(JSON.parse(cached)) } catch {}
    }
    // Then verify with backend
    refreshUser()
  }, [refreshUser])

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch(`${getApiBase()}/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data?.detail || `Login failed (${res.status})`)
    }

    const { token, user: userData } = await res.json()
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData))
    setUser(userData)
  }, [])

  const logout = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      // Best-effort server-side logout
      try {
        await fetch(`${getApiBase()}/v1/auth/logout`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        })
      } catch {}
    }
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_STORAGE_KEY)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{
      user,
      isAuthenticated: !!user,
      isLoading,
      login,
      logout,
      refreshUser,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
