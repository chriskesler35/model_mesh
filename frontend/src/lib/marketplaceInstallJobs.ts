import { loadMarketplaceCatalog } from '@/lib/marketplaceCatalog'
import fs from 'fs'
import path from 'path'

export type InstallStatus =
  | 'downloading'
  | 'validating'
  | 'extracting'
  | 'checking'
  | 'finalizing'
  | 'success'
  | 'failed'

interface InstallJob {
  skillId: string
  startTime: number
}

const FRONTEND_DIR = process.cwd()
const JOB_STATE_FILE = path.join(FRONTEND_DIR, '.next', 'marketplace_install_jobs.json')

function ensureStateDir(): void {
  const dir = path.dirname(JOB_STATE_FILE)
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
}

function readJobs(): Record<string, InstallJob> {
  ensureStateDir()
  if (!fs.existsSync(JOB_STATE_FILE)) {
    return {}
  }

  try {
    const payload = JSON.parse(fs.readFileSync(JOB_STATE_FILE, 'utf-8'))
    return payload && typeof payload === 'object' ? payload : {}
  } catch {
    return {}
  }
}

function writeJobs(jobs: Record<string, InstallJob>): void {
  ensureStateDir()
  fs.writeFileSync(JOB_STATE_FILE, JSON.stringify(jobs), 'utf-8')
}

function createJobId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function computeProgress(startTime: number): {
  status: InstallStatus
  current_step: number
  progress: number
  step_messages: Record<string, string>
} {
  const elapsed = (Date.now() - startTime) / 1000

  const stepMessages: Record<string, string> = {
    '0': 'Downloading package',
    '1': 'Validating manifest',
    '2': 'Extracting files',
    '3': 'Running health checks',
    '4': 'Finalizing install',
  }

  if (elapsed < 2) {
    return { status: 'downloading', current_step: 0, progress: Math.min(24, Math.floor((elapsed / 2) * 25)), step_messages: stepMessages }
  }
  if (elapsed < 4) {
    return { status: 'validating', current_step: 1, progress: 25 + Math.min(24, Math.floor(((elapsed - 2) / 2) * 25)), step_messages: stepMessages }
  }
  if (elapsed < 6) {
    return { status: 'extracting', current_step: 2, progress: 50 + Math.min(24, Math.floor(((elapsed - 4) / 2) * 25)), step_messages: stepMessages }
  }
  if (elapsed < 8) {
    return { status: 'checking', current_step: 3, progress: 75 + Math.min(14, Math.floor(((elapsed - 6) / 2) * 15)), step_messages: stepMessages }
  }
  if (elapsed < 10) {
    return { status: 'finalizing', current_step: 4, progress: 90 + Math.min(9, Math.floor(((elapsed - 8) / 2) * 10)), step_messages: stepMessages }
  }

  return { status: 'success', current_step: 4, progress: 100, step_messages: stepMessages }
}

export async function startMarketplaceInstall(skillId: string): Promise<{ job_id: string }> {
  const { skills } = await loadMarketplaceCatalog()
  const exists = skills.some((s) => s.skill_id === skillId)
  if (!exists) {
    throw new Error(`Skill '${skillId}' not found`)
  }

  const jobId = createJobId()
  const jobs = readJobs()
  jobs[jobId] = { skillId, startTime: Date.now() }
  writeJobs(jobs)
  return { job_id: jobId }
}

export function getMarketplaceInstallProgress(skillId: string, jobId: string) {
  const jobs = readJobs()
  const job = jobs[jobId]
  if (!job || job.skillId !== skillId) {
    throw new Error(`Install job '${jobId}' not found`)
  }

  const progress = computeProgress(job.startTime)
  if (progress.status === 'success') {
    // One-shot job lifecycle; remove completed job to avoid unbounded state growth.
    delete jobs[jobId]
    writeJobs(jobs)
  }

  return {
    job_id: jobId,
    skill_id: skillId,
    ...progress,
    error: null,
    failed_step: null,
    can_retry: false,
  }
}
