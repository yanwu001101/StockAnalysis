import request from './request'

export interface SchedulerJob {
  id: string
  next_run_time?: string | null
  trigger: string
}

export interface JobRun {
  id: string
  job: string
  status: 'running' | 'success' | 'partial' | 'failed' | 'skipped' | 'unknown'
  started_at: string
  finished_at?: string | null
  duration_s?: number | null
  error?: string | null
  reason?: string | null
  outcome_version?: number
  rows?: number | null
  universe_size?: number | null
  steps?: unknown
  row_semantics?: string
  outcome?: Record<string, unknown>
}

export function listSchedulerJobs(): Promise<{ jobs: SchedulerJob[]; running: boolean; valid_runs?: string[] }> {
  return request.get('/admin/tasks/jobs')
}

export function runJob(job: string): Promise<JobRun> {
  return request.post('/admin/tasks/run', { job })
}

export function listRuns(): Promise<{ items: JobRun[] }> {
  return request.get('/admin/tasks/runs')
}

export function clearCache(pattern: string) {
  return request.post('/admin/tasks/cache/clear', null, { params: { pattern } })
}
