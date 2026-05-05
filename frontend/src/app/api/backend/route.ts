/**
 * Backend process control — runs on the Next.js server (port 3001), not the Python backend.
 * This means it works even when the backend (default port 19001) is completely down.
 */

import { NextRequest, NextResponse } from 'next/server'
import { exec, spawn } from 'child_process'
import { promisify } from 'util'
import path from 'path'
import fs from 'fs'

const execAsync = promisify(exec)

const PRIMARY_BACKEND_PORT = 19001
const LEGACY_BACKEND_PORT = 19000
const BACKEND_PORTS = [PRIMARY_BACKEND_PORT, LEGACY_BACKEND_PORT]

// Resolve paths from process.cwd() (frontend directory) → sibling backend
// In dev: cwd = G:\Model_Mesh\frontend, backend = G:\Model_Mesh\backend
const FRONTEND_DIR = process.cwd()
const REPO_ROOT = path.resolve(FRONTEND_DIR, '..')
const BACKEND_DIR = path.join(REPO_ROOT, 'backend')
const LOGS_DIR = path.join(REPO_ROOT, 'logs')
const BACKEND_STARTUP_LOG = path.join(LOGS_DIR, 'backend-startup.log')
// The virtual environment lives at <repo_root>/.venv, not backend/venv.
const VENV_PYTHON = fs.existsSync(path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'))
  ? path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe')
  : path.join(BACKEND_DIR, 'venv', 'Scripts', 'python.exe') // legacy fallback
const PYTHON_EXE = 'C:\\Python313\\python.exe' // last-resort fallback
const FALLBACK_ENV = (process.env.DEVFORGE_ALLOW_BACKEND_PYTHON_FALLBACK || '').toLowerCase()
const FALLBACK_ENV_SET = FALLBACK_ENV.length > 0
const ALLOW_BACKEND_PYTHON_FALLBACK = FALLBACK_ENV_SET
  ? ['1', 'true', 'yes', 'on'].includes(FALLBACK_ENV)
  : process.env.NODE_ENV !== 'production'

console.log('[backend route] Paths:', { REPO_ROOT, BACKEND_DIR, VENV_PYTHON, exists: fs.existsSync(VENV_PYTHON) })

// ── Helpers ──────────────────────────────────────────────────────────────────

async function getBackendPidForPort(port: number): Promise<number | null> {
  try {
    const { stdout } = await execAsync(
      `netstat -ano | findstr ":${port}" | findstr "LISTENING"`,
      { shell: 'cmd.exe' }
    )
    const parts = stdout.trim().split(/\s+/)
    const pid = parseInt(parts[parts.length - 1])
    return isNaN(pid) ? null : pid
  } catch {
    return null
  }
}

async function isBackendUp(): Promise<boolean> {
  const pid = await getBackendPidForPort(PRIMARY_BACKEND_PORT)
  return pid !== null
}

async function killBackends(): Promise<void> {
  const pids = new Set<number>()

  for (const port of BACKEND_PORTS) {
    const pid = await getBackendPidForPort(port)
    if (pid) pids.add(pid)
  }

  for (const pid of Array.from(pids)) {
    try {
      await execAsync(`taskkill /F /PID ${pid} /T`, { shell: 'cmd.exe' })
    } catch {
      // process may have already exited
    }
  }

  // Give Windows time to release sockets.
  await new Promise(r => setTimeout(r, 1500))
}

function getStartupLogTail(lines = 25): string[] {
  try {
    if (!fs.existsSync(BACKEND_STARTUP_LOG)) return []
    const content = fs.readFileSync(BACKEND_STARTUP_LOG, 'utf8')
    return content
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(-lines)
  } catch {
    return []
  }
}

function spawnBackend(explicitPythonExe?: string): { pythonExe: string; pid: number | null } {
  // Use venv python if it exists, fall back to system python
  const pythonExe = explicitPythonExe ?? (fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : PYTHON_EXE)
  console.log('[spawnBackend] Using python:', pythonExe, 'cwd:', BACKEND_DIR)

  fs.mkdirSync(LOGS_DIR, { recursive: true })
  const outFd = fs.openSync(BACKEND_STARTUP_LOG, 'a')

  const child = spawn(
    pythonExe,
    ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', String(PRIMARY_BACKEND_PORT)],
    {
      cwd: BACKEND_DIR,
      detached: true,
      stdio: ['ignore', outFd, outFd],
      windowsHide: true,
    }
  )
  fs.closeSync(outFd)
  child.unref()
  return { pythonExe, pid: child.pid ?? null }
}

async function isBackendHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`http://localhost:${PRIMARY_BACKEND_PORT}/`, { signal: AbortSignal.timeout(3000) })
    return res.ok
  } catch {
    return false
  }
}

async function waitForBackend(timeoutMs = 30000): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    await new Promise(r => setTimeout(r, 800))
    if (await isBackendUp()) {
      // Give app a little extra time to pass import/startup and answer HTTP.
      if (await isBackendHealthy()) return true
    }
  }
  return false
}

// ── Route handlers ────────────────────────────────────────────────────────────

export async function GET() {
  const pid = await getBackendPidForPort(PRIMARY_BACKEND_PORT)
  const legacyPid = await getBackendPidForPort(LEGACY_BACKEND_PORT)
  let healthy = false

  if (pid) {
    try {
      const res = await fetch(`http://localhost:${PRIMARY_BACKEND_PORT}/`, { signal: AbortSignal.timeout(3000) })
      healthy = res.ok
    } catch { /* unreachable */ }
  }

  return NextResponse.json({
    running: pid !== null,
    healthy,
    pid: pid ?? null,
    port: PRIMARY_BACKEND_PORT,
    staleLegacyPid: legacyPid ?? null,
  })
}

export async function POST(req: NextRequest) {
  const { action } = await req.json().catch(() => ({ action: 'start' }))

  if (action === 'start') {
    const already = await isBackendUp()
    if (already) {
      return NextResponse.json({
        ok: true,
        message: 'Already running',
        action,
        diagnostics: { alreadyRunning: true },
      })
    }

    const primaryAttempt = spawnBackend()
    let up = await waitForBackend()
    let fallbackUsed = false
    let fallbackAttempt: { pythonExe: string; pid: number | null } | null = null

    if (!up && ALLOW_BACKEND_PYTHON_FALLBACK && PYTHON_EXE !== VENV_PYTHON) {
      // Fallback one more time in case venv path is stale.
      fallbackUsed = true
      fallbackAttempt = spawnBackend(PYTHON_EXE)
      up = await waitForBackend(15000)
    }

    return NextResponse.json({
      ok: up,
      message: up ? 'Backend started' : 'Start timed out',
      action,
      diagnostics: {
        attemptedPython: primaryAttempt.pythonExe,
        attemptedPid: primaryAttempt.pid,
        fallbackAllowed: ALLOW_BACKEND_PYTHON_FALLBACK,
        fallbackUsed,
        fallbackPython: fallbackAttempt?.pythonExe ?? null,
        fallbackPid: fallbackAttempt?.pid ?? null,
        startupLogTail: up ? [] : getStartupLogTail(),
      },
    })
  }

  if (action === 'stop') {
    await killBackends()
    return NextResponse.json({ ok: true, message: 'Backend stopped', action })
  }

  if (action === 'restart') {
    await killBackends()
    const primaryAttempt = spawnBackend()
    let up = await waitForBackend()
    let fallbackUsed = false
    let fallbackAttempt: { pythonExe: string; pid: number | null } | null = null

    if (!up && ALLOW_BACKEND_PYTHON_FALLBACK && PYTHON_EXE !== VENV_PYTHON) {
      fallbackUsed = true
      fallbackAttempt = spawnBackend(PYTHON_EXE)
      up = await waitForBackend(15000)
    }

    return NextResponse.json({
      ok: up,
      message: up ? 'Backend restarted' : 'Restart timed out',
      action,
      diagnostics: {
        attemptedPython: primaryAttempt.pythonExe,
        attemptedPid: primaryAttempt.pid,
        fallbackAllowed: ALLOW_BACKEND_PYTHON_FALLBACK,
        fallbackUsed,
        fallbackPython: fallbackAttempt?.pythonExe ?? null,
        fallbackPid: fallbackAttempt?.pid ?? null,
        startupLogTail: up ? [] : getStartupLogTail(),
      },
    })
  }

  return NextResponse.json({ ok: false, message: `Unknown action: ${action}` }, { status: 400 })
}
