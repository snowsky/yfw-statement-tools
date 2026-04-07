import { apiRequest } from '@/lib/api/_base'
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

  /** Poll for the current status of a batch job. */
  getJobStatus: (jobId: string): Promise<BatchJobStatus> =>
    apiRequest<BatchJobStatus>(`${PREFIX}/batch/jobs/${jobId}`),

  /** Build the public download URL for a token. */
  downloadUrl: (token: string): string =>
    `/api/v1${PREFIX}/statements/download/${token}`,
}
