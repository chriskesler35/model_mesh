import { NextResponse } from 'next/server'
import { loadMarketplaceCatalog } from '@/lib/marketplaceCatalog'

export async function GET() {
  const { skills, source } = await loadMarketplaceCatalog()

  const useCases = new Set<string>()
  const languages = new Set<string>()
  const complexityLevels = new Set<string>()
  const trustLevels = new Set<string>()

  for (const skill of skills) {
    skill.use_cases.forEach((item) => useCases.add(item))
    skill.languages.forEach((item) => languages.add(item))
    if (skill.complexity) complexityLevels.add(skill.complexity)
    if (skill.trust_level) trustLevels.add(skill.trust_level)
  }

  return NextResponse.json({
    use_cases: Array.from(useCases).sort(),
    languages: Array.from(languages).sort(),
    complexity_levels: Array.from(complexityLevels).sort(),
    trust_levels: Array.from(trustLevels).sort(),
    source,
  })
}
