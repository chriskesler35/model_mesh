/**
 * Frontend health + self-healing endpoint.
 *
 * GET  /api/health — returns frontend health status + backend connectivity
 * POST /api/health — triggers self-healing actions (clear cache, etc.)
 */

import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const FRONTEND_DIR = process.cwd()
const NEXT_DIR = path.join(FRONTEND_DIR, '.next')
const CACHE_DIR = path.join(NEXT_DIR, 'cache')
const BACKEND_PORT = 19000

export async function GET() {
  let backendHealthy = false
  try {
    const res = await fetch(`http://localhost:${BACKEND_PORT}/`, {
      signal: AbortSignal.timeout(3000),
    })
    backendHealthy = res.ok
  } catch { /* backend unreachable */ }

  const cacheExists = fs.existsSync(CACHE_DIR)
  const nextExists = fs.existsSync(NEXT_DIR)

  return NextResponse.json({
    status: 'ok',
    frontend: 'running',
    backend: backendHealthy ? 'healthy' : 'unreachable',
    cache: cacheExists ? 'present' : 'clean',
    buildDir: nextExists,
    timestamp: new Date().toISOString(),
  })
}

export async function POST(req: NextRequest) {
  const { action } = await req.json().catch(() => ({ action: 'clear-cache' }))

  if (action === 'clear-cache') {
    try {
      if (fs.existsSync(CACHE_DIR)) {
        fs.rmSync(CACHE_DIR, { recursive: true, force: true })
        return NextResponse.json({
          ok: true,
          message: 'Cache cleared. Reload the page to complete recovery.',
          action,
        })
      }
      return NextResponse.json({ ok: true, message: 'Cache already clean.', action })
    } catch (e: any) {
      return NextResponse.json({ ok: false, message: e.message, action }, { status: 500 })
    }
  }

  return NextResponse.json({ ok: false, message: `Unknown action: ${action}` }, { status: 400 })
}
