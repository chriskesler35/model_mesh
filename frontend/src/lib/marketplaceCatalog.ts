import fs from 'fs'
import path from 'path'

export interface MarketplaceSkill {
  skill_id: string
  name: string
  description: string
  version: string
  use_cases: string[]
  languages: string[]
  complexity: string
  trust_level: string
  install_url: string
  manifest_url: string
  icon_url?: string
}

const FRONTEND_DIR = process.cwd()
const REPO_ROOT = path.resolve(FRONTEND_DIR, '..')
const LOCAL_CATALOG_PATH = path.join(REPO_ROOT, 'backend', 'skills_catalog.json')

function toStringOrEmpty(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function deriveManifestUrlFromInstallUrl(installUrl: string): string {
  const url = installUrl.trim()
  if (!url) return ''

  const githubMatch = url.match(/^https?:\/\/github\.com\/([^/]+)\/([^/?#]+)/i)
  if (!githubMatch) return ''

  const owner = githubMatch[1]
  const repo = githubMatch[2].replace(/\.git$/i, '')
  return `https://raw.githubusercontent.com/${owner}/${repo}/main/manifest.json`
}

function resolveManifestUrl(raw: any, installUrl: string): string {
  const direct = toStringOrEmpty(raw?.manifest_url || raw?.manifestUrl)
  if (direct) return direct
  return deriveManifestUrlFromInstallUrl(installUrl)
}

function normalizeSkill(raw: any): MarketplaceSkill | null {
  if (!raw || typeof raw !== 'object' || !raw.skill_id || !raw.name) {
    return null
  }

  const installUrl = toStringOrEmpty(raw.install_url || raw.installUrl)
  const manifestUrl = resolveManifestUrl(raw, installUrl)

  return {
    skill_id: String(raw.skill_id),
    name: String(raw.name),
    description: String(raw.description || ''),
    version: String(raw.version || '0.0.0'),
    use_cases: Array.isArray(raw.use_cases) ? raw.use_cases.map(String) : [],
    languages: Array.isArray(raw.languages) ? raw.languages.map(String) : [],
    complexity: String(raw.complexity || 'unknown'),
    trust_level: String(raw.trust_level || 'community'),
    install_url: installUrl,
    manifest_url: manifestUrl,
    icon_url: raw.icon_url ? String(raw.icon_url) : undefined,
  }
}

export async function loadMarketplaceCatalog(): Promise<{ source: string; skills: MarketplaceSkill[] }> {
  const remoteCatalogUrl =
    process.env.SKILLS_MARKETPLACE_URL || process.env.NEXT_PUBLIC_SKILLS_MARKETPLACE_URL

  if (remoteCatalogUrl) {
    try {
      const response = await fetch(remoteCatalogUrl, { cache: 'no-store' })
      if (!response.ok) {
        throw new Error(`Remote catalog returned ${response.status}`)
      }

      const payload = await response.json()
      const list = Array.isArray(payload) ? payload : payload?.skills
      if (!Array.isArray(list)) {
        throw new Error('Remote catalog payload must be an array or { skills: [] }')
      }

      const skills = list
        .map(normalizeSkill)
        .filter((s): s is MarketplaceSkill => s !== null)

      return { source: `remote:${remoteCatalogUrl}`, skills }
    } catch {
      // Fall back to local catalog if remote is unavailable.
    }
  }

  if (!fs.existsSync(LOCAL_CATALOG_PATH)) {
    return { source: `missing:${LOCAL_CATALOG_PATH}`, skills: [] }
  }

  try {
    const rawText = fs.readFileSync(LOCAL_CATALOG_PATH, 'utf-8')
    const payload = JSON.parse(rawText)
    const list = Array.isArray(payload) ? payload : payload?.skills
    const skills = Array.isArray(list)
      ? list.map(normalizeSkill).filter((s): s is MarketplaceSkill => s !== null)
      : []

    return { source: `local:${LOCAL_CATALOG_PATH}`, skills }
  } catch {
    return { source: `invalid:${LOCAL_CATALOG_PATH}`, skills: [] }
  }
}

export function filterMarketplaceSkills(
  skills: MarketplaceSkill[],
  options: {
    search_query?: string
    use_cases?: string
    languages?: string
    complexity?: string
    trust_level?: string
  }
): MarketplaceSkill[] {
  let results = [...skills]

  if (options.search_query) {
    const query = options.search_query.toLowerCase()
    results = results.filter((s) =>
      s.name.toLowerCase().includes(query) || s.description.toLowerCase().includes(query)
    )
  }

  if (options.use_cases) {
    const selectedUseCases = options.use_cases
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    results = results.filter((s) => selectedUseCases.some((uc) => s.use_cases.includes(uc)))
  }

  if (options.languages) {
    const selectedLanguages = options.languages
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    results = results.filter((s) => selectedLanguages.some((lang) => s.languages.includes(lang)))
  }

  if (options.complexity) {
    results = results.filter((s) => s.complexity === options.complexity)
  }

  if (options.trust_level) {
    results = results.filter((s) => s.trust_level === options.trust_level)
  }

  return results
}
