import { apiRequest, apiBlobRequest } from '@/lib/api/_base'
import type { BatchJobStatus, BatchUploadResponse, UploadResponse } from '@/types'

const PREFIX = '/statement-tools'

export const statementsApi = {
  /**
   * Upload one or more files. Backend forwards each to YFW for AI parsing,
   * merges transactions, returns a download link valid for the configured
   * retention period (default: 1 hour).
   */
  upload: (files: File[]): Promise<UploadResponse> => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    return apiRequest<UploadResponse>(`${PREFIX}/statements/upload`, {
      method: 'POST',
      body: form,
    })
  },

  /**
   * Upload multiple files for a background batch processing job.
   */
  uploadBatch: (files: File[]): Promise<BatchUploadResponse> => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    return apiRequest<BatchUploadResponse>(`${PREFIX}/batch/upload`, {
      method: 'POST',
      body: form,
    })
  },

  /** Fetch server-side job history for the authenticated user (empty for public visitors). */
  listJobs: (limit = 50): Promise<{ jobs: Array<{ job_id: string; status: string; total_files: number; created_at: string }>; total: number }> =>
    apiRequest(`${PREFIX}/batch/jobs?limit=${limit}`),

  /** Poll for the current status of a batch job. */
  getJobStatus: (jobId: string): Promise<BatchJobStatus> =>
    apiRequest<BatchJobStatus>(`${PREFIX}/batch/jobs/${jobId}`),

  /** Build the public download URL for a token. */
  downloadUrl: (token: string): string =>
    `/api/v1${PREFIX}/statements/download/${token}`,

  /** Download a completed batch job's transactions as a CSV Blob. */
  downloadJobCsv: (jobId: string): Promise<Blob> =>
    apiBlobRequest(`${PREFIX}/batch/jobs/${jobId}/csv`),

  /** Merge transactions from multiple jobs into a single CSV Blob. */
  mergeJobsCsv: (jobIds: string[]): Promise<Blob> =>
    apiBlobRequest(`${PREFIX}/batch/merge-csv`, {
      method: 'POST',
      body: JSON.stringify({ job_ids: jobIds }),
      headers: { 'Content-Type': 'application/json' },
    }),
}
