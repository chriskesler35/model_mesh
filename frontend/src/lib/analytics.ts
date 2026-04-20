type AnalyticsPayload = Record<string, unknown>

export function trackEvent(event: string, payload: AnalyticsPayload = {}): void {
  if (typeof window === 'undefined') return

  const detail = {
    event,
    payload,
    ts: new Date().toISOString(),
  }

  try {
    window.dispatchEvent(new CustomEvent('devforgeai:analytics', { detail }))
  } catch {
    // no-op
  }

  if (process.env.NODE_ENV !== 'production') {
    try {
      // Keep instrumentation visible during development while backend analytics is added.
      console.debug('[analytics]', detail)
    } catch {
      // no-op
    }
  }
}
