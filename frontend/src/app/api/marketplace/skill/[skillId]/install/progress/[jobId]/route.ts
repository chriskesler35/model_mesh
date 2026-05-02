import { NextRequest, NextResponse } from 'next/server'
import { getMarketplaceInstallProgress } from '@/lib/marketplaceInstallJobs'

export async function GET(
  _request: NextRequest,
  context: { params: { skillId: string; jobId: string } }
) {
  const { skillId, jobId } = context.params

  try {
    const payload = getMarketplaceInstallProgress(skillId, jobId)
    return NextResponse.json(payload)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to fetch install progress'
    const status = message.includes('not found') ? 404 : 500
    return NextResponse.json({ detail: message }, { status })
  }
}
