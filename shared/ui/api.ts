/**
 * Statement-tools API client.
 *
 * All calls go to the statement-tools backend (VITE_API_URL in standalone,
 * same origin in plugin mode). The backend forwards files to YFW for parsing.
 */

import { API_PREFIX, BASE_URL } from "./config";
import { authHeaders } from "./setup";

// ── Types ────────────────────────────────────────────────────────────────────

export interface UploadResponse {
  success: boolean;
  message: string;
  transaction_count: number;
  file_count: number;
  download_url: string;
  expires_at: string;
  errors: string[];
}

export interface BatchUploadResponse {
  success: boolean;
  job_id: string;
  status: string;
  message?: string;
}

export interface BatchFileStatus {
  id: number;
  filename: string;
  status: string;
  error_message?: string;
  extracted_data?: any;
}

export interface BatchJobStatus {
  job_id: string;
  status: string;
  processed_files: number;
  total_files: number;
  successful_files: number;
  failed_files: number;
  progress_percentage: number;
  files: BatchFileStatus[];
  completed_at?: string;
}

// ── API methods ──────────────────────────────────────────────────────────────

export const statementToolsApi = {
  /**
   * Upload one or more files. Backend forwards each to YFW for AI parsing,
   * merges transactions, returns a download link valid for 1 hour.
   * @deprecated Use uploadBatch for larger files or multiple files.
   */
  upload: async (files: File[]): Promise<UploadResponse> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);

    const res = await fetch(`${BASE_URL}${API_PREFIX}/statements/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<UploadResponse>;
  },

  /**
   * Upload multiple files for a background batch processing job.
   */
  uploadBatch: async (files: File[]): Promise<BatchUploadResponse> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);

    const res = await fetch(`${BASE_URL}${API_PREFIX}/batch/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<BatchUploadResponse>;
  },

  /**
   * Get the current status of a batch job.
   */
  getJobStatus: async (jobId: string): Promise<BatchJobStatus> => {
    const res = await fetch(`${BASE_URL}${API_PREFIX}/batch/jobs/${jobId}`, {
      method: "GET",
      headers: authHeaders(),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<BatchJobStatus>;
  },

  /** Build the full download URL for a given relative path. */
  downloadUrl: (relativePath: string) => `${BASE_URL}${relativePath}`,
};

/** Test connectivity via the standalone backend (avoids browser CORS issues). */
export async function testConnection(
  apiUrl: string,
  apiKey: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(`${BASE_URL}${API_PREFIX}/check-connection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yfw_api_url: apiUrl, yfw_api_key: apiKey }),
    });
    if (!res.ok) return { ok: false, error: `Backend returned HTTP ${res.status}` };
    return res.json();
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}
