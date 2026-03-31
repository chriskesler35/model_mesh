'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback, createContext, useContext } from 'react'


interface Toast {
  id: string
  type: 'success' | 'error' | 'info'
  title: string
  message: string
  taskId?: string
  result?: any
  dismissible?: boolean
  autoClose?: number  // ms
}

interface ToastContextType {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => void
  dismissToast: (id: string) => void
  submitTask: (taskType: string, params: any, conversationId?: string) => Promise<string>
}

const ToastContext = createContext<ToastContextType>({
  toasts: [],
  addToast: () => {},
  dismissToast: () => {},
  submitTask: async () => '',
})

export function useToast() {
  return useContext(ToastContext)
}

export default function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [polledIds, setPolledIds] = useState<Set<string>>(new Set())

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    setToasts(prev => [...prev, { ...toast, id }])

    if (toast.autoClose !== 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id))
      }, toast.autoClose || 8000)
    }
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
    // If it's a task notification, acknowledge it on the server
    const toast = toasts.find(t => t.id === id)
    if (toast?.taskId) {
      fetch(`${API_BASE}/v1/tasks/${toast.taskId}/acknowledge`, {
        method: 'POST', headers: AUTH_HEADERS,
      }).catch(() => {})
    }
  }, [toasts])

  const submitTask = useCallback(async (taskType: string, params: any, conversationId?: string): Promise<string> => {
    const res = await fetch(`${API_BASE}/v1/tasks`, {
      method: 'POST',
      headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_type: taskType, params, conversation_id: conversationId }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.detail || 'Failed to submit task')

    addToast({
      type: 'info',
      title: 'Task submitted',
      message: data.user_message || `${taskType} started…`,
      autoClose: 4000,
    })

    return data.id
  }, [addToast])

  // Poll for completed tasks every 5s
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/tasks/notifications`, { headers: AUTH_HEADERS })
        if (!res.ok) return
        const data = await res.json()
        for (const task of data.notifications || []) {
          if (polledIds.has(task.id)) continue
          setPolledIds(prev => new Set(prev).add(task.id))

          addToast({
            type: task.status === 'completed' ? 'success' : 'error',
            title: task.status === 'completed' ? '✅ Task complete' : '❌ Task failed',
            message: task.user_message || (task.error ? `Error: ${task.error}` : 'Done'),
            taskId: task.id,
            result: task.result,
            autoClose: 0,  // Stay until dismissed
            dismissible: true,
          })

          // Auto-acknowledge on the server
          fetch(`${API_BASE}/v1/tasks/${task.id}/acknowledge`, {
            method: 'POST', headers: AUTH_HEADERS,
          }).catch(() => {})
        }
      } catch { /* silent */ }
    }

    poll()
    const interval = setInterval(poll, 5000)
    return () => clearInterval(interval)
  }, [polledIds, addToast])

  return (
    <ToastContext.Provider value={{ toasts, addToast, dismissToast, submitTask }}>
      {children}

      {/* Toast container — fixed bottom-right, renders on all pages */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map(toast => (
          <div
            key={toast.id}
            className={`pointer-events-auto rounded-xl shadow-lg border px-4 py-3 flex items-start gap-3 animate-slide-in ${
              toast.type === 'success'
                ? 'bg-white dark:bg-gray-800 border-green-200 dark:border-green-700'
                : toast.type === 'error'
                ? 'bg-white dark:bg-gray-800 border-red-200 dark:border-red-700'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
            }`}
          >
            <div className="flex-shrink-0 text-lg mt-0.5">
              {toast.type === 'success' ? '✅' : toast.type === 'error' ? '❌' : 'ℹ️'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-900 dark:text-white">{toast.title}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 break-words">{toast.message}</p>
              {toast.result?.url && (
                <a
                  href={`${API_BASE}${toast.result.url}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-block mt-1.5 text-xs text-orange-600 dark:text-orange-400 hover:underline"
                >
                  View result →
                </a>
              )}
            </div>
            <button
              onClick={() => dismissToast(toast.id)}
              className="flex-shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xs p-1"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {/* Slide-in animation */}
      <style jsx global>{`
        @keyframes slide-in {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        .animate-slide-in {
          animation: slide-in 0.3s ease-out;
        }
      `}</style>
    </ToastContext.Provider>
  )
}
