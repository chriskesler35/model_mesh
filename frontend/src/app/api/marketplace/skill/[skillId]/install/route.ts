import { NextRequest, NextResponse } from 'next/server'
import { startMarketplaceInstall } from '@/lib/marketplaceInstallJobs'

export async function POST(
  _request: NextRequest,
  context: { params: { skillId: string } }
) {
  const skillId = context.params.skillId

  try {
    const payload = await startMarketplaceInstall(skillId)
    return NextResponse.json(payload)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to start install'
    const status = message.includes('not found') ? 404 : 500
    return NextResponse.json({ detail: message }, { status })
  }
}
