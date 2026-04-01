/**
 * Backend process control — runs on the Next.js server (port 3001), not the Python backend.
 * This means it works even when the backend (port 19000) is completely down.
 */

import { NextRequest, NextResponse } from 'next/server'
import { exec, spawn } from 'child_process'
import { promisify } from 'util'

const execAsync = promisify(exec)

const BACKEND_PORT = 19000
const PYTHON_EXE  = 'C:\\Python313\\python.exe'
// Resolve relative to this file: frontend/src/app/api/backend/ → ../../../../.. → repo root → backend
const REPO_ROOT   = require('path').resolve(__dirname, '..', '..', '..', '..', '..', '..', '..')
const BACKEND_DIR = require('path').join(REPO_ROOT, 'backend')
const VENV_PYTHON = require('path').join(BACKEND_DIR, 'venv', 'Scripts', 'python.exe')

// ── Helpers ──────────────────────────────────────────────────────────────────

async function getBackendPid(): Promise<number | null> {
  try {
    const { stdout } = await execAsync(
      `netstat -ano | findstr ":${BACKEND_PORT}" | findstr "LISTENING"`,
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
  const pid = await getBackendPid()
  return pid !== null
}

async function killBackend(): Promise<void> {
  const pid = await getBackendPid()
  if (pid) {
    try {
      await execAsync(`taskkill /F /PID ${pid}`, { shell: 'cmd.exe' })
      // Wait for port to free
      await new Promise(r => setTimeout(r, 1500))
    } catch { /* already dead */ }
  }
}

function spawnBackend(): void {
  // Use venv python if it exists, fall back to system python
  const fs = require('fs')
  const pythonExe = fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : PYTHON_EXE
  const child = spawn(pythonExe, ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', String(BACKEND_PORT)], {
    cwd: BACKEND_DIR,
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    shell: false,
  })
  child.unref()
}

async function waitForBackend(timeoutMs = 30000): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    await new Promise(r => setTimeout(r, 800))
    if (await isBackendUp()) return true
  }
  return false
}

// ── Route handlers ────────────────────────────────────────────────────────────

export async function GET() {
  const pid = await getBackendPid()
  let healthy = false

  if (pid) {
    try {
      const res = await fetch(`http://localhost:${BACKEND_PORT}/`, { signal: AbortSignal.timeout(3000) })
      healthy = res.ok
    } catch { /* unreachable */ }
  }

  return NextResponse.json({
    running: pid !== null,
    healthy,
    pid: pid ?? null,
    port: BACKEND_PORT,
  })
}

export async function POST(req: NextRequest) {
  const { action } = await req.json().catch(() => ({ action: 'start' }))

  if (action === 'start') {
    const already = await isBackendUp()
    if (already) return NextResponse.json({ ok: true, message: 'Already running', action })
    spawnBackend()
    const up = await waitForBackend()
    return NextResponse.json({ ok: up, message: up ? 'Backend started' : 'Start timed out', action })
  }

  if (action === 'stop') {
    await killBackend()
    return NextResponse.json({ ok: true, message: 'Backend stopped', action })
  }

  if (action === 'restart') {
    await killBackend()
    spawnBackend()
    const up = await waitForBackend()
    return NextResponse.json({ ok: up, message: up ? 'Backend restarted' : 'Restart timed out', action })
  }

  return NextResponse.json({ ok: false, message: `Unknown action: ${action}` }, { status: 400 })
}
