import type { SavedJob } from '@/types'

const STORAGE_KEY = 'statement_tools_job_history'
const MAX_JOBS = 50

export function loadJobs(): SavedJob[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

export function saveJob(job: SavedJob): void {
  const existing = loadJobs()
  const deduped = [job, ...existing.filter(j => j.job_id !== job.job_id)]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(deduped.slice(0, MAX_JOBS)))
}

export function updateJobStatus(job_id: string, status: string): void {
  const jobs = loadJobs()
  const updated = jobs.map(j => j.job_id === job_id ? { ...j, status } : j)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
}

export function removeJob(job_id: string): void {
  const jobs = loadJobs().filter(j => j.job_id !== job_id)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs))
}
