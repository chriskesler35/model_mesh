import { NextRequest, NextResponse } from 'next/server'
import { filterMarketplaceSkills, loadMarketplaceCatalog } from '@/lib/marketplaceCatalog'

export async function GET(request: NextRequest) {
  const { skills, source } = await loadMarketplaceCatalog()

  const params = request.nextUrl.searchParams
  const results = filterMarketplaceSkills(skills, {
    search_query: params.get('search_query') || undefined,
    use_cases: params.get('use_cases') || undefined,
    languages: params.get('languages') || undefined,
    complexity: params.get('complexity') || undefined,
    trust_level: params.get('trust_level') || undefined,
  })

  return NextResponse.json({
    total: results.length,
    results,
    source,
  })
}
