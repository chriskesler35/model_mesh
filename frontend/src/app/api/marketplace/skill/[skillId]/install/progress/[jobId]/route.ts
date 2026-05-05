import { NextRequest, NextResponse } from 'next/server'

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_URL?.trim() || 'http://localhost:19001'

export async function GET(
  _request: NextRequest,
  context: { params: { skillId: string; jobId: string } }
) {
  const { skillId, jobId } = context.params

  try {
    const res = await fetch(
      `${BACKEND_BASE}/v1/marketplace/skill/${encodeURIComponent(skillId)}/install/progress/${encodeURIComponent(jobId)}`,
      { cache: 'no-store' }
    )
    const payload = await res.json()
    return NextResponse.json(payload, { status: res.ok ? 200 : res.status })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to fetch install progress'
    return NextResponse.json({ detail: message }, { status: 500 })
  }
}
