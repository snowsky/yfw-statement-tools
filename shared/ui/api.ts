/**
 * Statement-tools API client.
 *
 * All calls go to the statement-tools backend (VITE_API_URL in standalone,
 * same origin in plugin mode). The backend forwards files to YFW for parsing.
 */

import { STORAGE_KEYS, API_PREFIX, BASE_URL } from "./config";
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

// ── Core fetch utility ────────────────────────────────────────────────────────

/**
 * Core fetch utility that handles both standalone (with API key) 
 * and plugin (with session auth) environments.
 */
export async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const isStandalone = !!localStorage.getItem(STORAGE_KEYS.apiKey);
  const fullUrl = isStandalone ? `${BASE_URL}${path}` : path;
  
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string> || {}),
  };

  if (isStandalone) {
    const apiKey = localStorage.getItem(STORAGE_KEYS.apiKey);
    if (apiKey) {
      headers["X-API-Key"] = apiKey;
    }
  }

  const res = await fetch(fullUrl, {
    ...opts,
    headers: {
      ...authHeaders(),
      ...headers
    }
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail?.detail ?? `HTTP ${res.status}`);
  }

  if (res.status === 204) return undefined as unknown as T;
  return res.json();
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
    return apiFetch<UploadResponse>(`${API_PREFIX}/statements/upload`, {
      method: "POST",
      body: form,
    });
  },

  /**
   * Upload multiple files for a background batch processing job.
   */
  uploadBatch: async (files: File[]): Promise<BatchUploadResponse> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    return apiFetch<BatchUploadResponse>(`${API_PREFIX}/batch/upload`, {
      method: "POST",
      body: form,
    });
  },

  /**
   * Get the current status of a batch job.
   */
  getJobStatus: (jobId: string): Promise<BatchJobStatus> =>
    apiFetch<BatchJobStatus>(`${API_PREFIX}/batch/jobs/${jobId}`),

  /** Build the full download URL for a given relative path. */
  downloadUrl: (relativePath: string) => {
    const isStandalone = !!localStorage.getItem(STORAGE_KEYS.apiKey);
    return isStandalone ? `${BASE_URL}${relativePath}` : relativePath;
  },
};

/** Test connectivity via the standalone backend (avoids browser CORS issues). */
export async function testConnection(
  apiUrl: string,
  apiKey: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    return apiFetch<{ ok: boolean; error?: string }>(`${API_PREFIX}/check-connection`, {
      method: "POST",
      body: JSON.stringify({ yfw_api_url: apiUrl, yfw_api_key: apiKey }),
    });
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}
