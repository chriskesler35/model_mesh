type FeatureFlags = {
  uiGuidedMode: boolean
  methodLauncherV1: boolean
  skillsMarketplaceAlpha: boolean
}

function envFlag(value: string | undefined, fallback: boolean): boolean {
  if (typeof value !== 'string') return fallback
  const normalized = value.trim().toLowerCase()
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false
  return fallback
}

export const featureFlags: FeatureFlags = {
  // Guided mode defaults on while we improve onboarding/launch flow.
  uiGuidedMode: envFlag(process.env.NEXT_PUBLIC_UI_GUIDED_MODE, true),
  // New method launcher recommendation UX.
  methodLauncherV1: envFlag(process.env.NEXT_PUBLIC_METHOD_LAUNCHER_V1, false),
  // Skills/tools marketplace alpha.
  skillsMarketplaceAlpha: envFlag(process.env.NEXT_PUBLIC_SKILLS_MARKETPLACE_ALPHA, false),
}
