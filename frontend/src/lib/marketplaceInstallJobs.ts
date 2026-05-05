/**
 * Marketplace install job helpers — delegates to the real Python backend.
 * The backend's POST /v1/marketplace/skill/{id}/install writes to
 * data/installed_skills.json synchronously, then the progress endpoint
 * animates a smooth UX and returns success.
 */

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_URL?.trim() || 'http://localhost:19001'

export type InstallStatus =
  | 'downloading'
  | 'validating'
  | 'extracting'
  | 'checking'
  | 'finalizing'
  | 'success'
  | 'failed'

export async function startMarketplaceInstall(skillId: string): Promise<{ job_id: string }> {
  const res = await fetch(`${BACKEND_BASE}/v1/marketplace/skill/${encodeURIComponent(skillId)}/install`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Install failed (HTTP ${res.status})`)
  }
  return res.json()
}

export function getMarketplaceInstallProgress(skillId: string, jobId: string) {
  // This function is called from a Next.js route handler (server side).
  // We can't do async fetch here because the route handler already awaited
  // startMarketplaceInstall; this function just tells the client to poll
  // the backend progress endpoint directly.
  //
  // Return a synthetic "in-progress" payload so the frontend starts polling
  // the backend endpoint (GET /v1/marketplace/skill/{id}/install/progress/{jobId}).
  return {
    job_id: jobId,
    skill_id: skillId,
    status: 'downloading' as InstallStatus,
    current_step: 0,
    progress: 0,
    step_messages: { '0': '→ Starting install…' },
    error: null,
    failed_step: null,
    can_retry: false,
  }
}

