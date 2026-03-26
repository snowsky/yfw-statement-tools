/**
 * Statement-tools API client.
 *
 * All calls go to the statement-tools backend (VITE_API_URL in standalone,
 * same origin in plugin mode). The backend proxies to YFW internally.
 */

const BASE_URL =
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_URL) || "";

const PREFIX = "/api/v1/statement-tools";

// ── Auth header ──────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  const key = localStorage.getItem("yfw_api_key");
  return key ? { "X-API-Key": key } : {};
}

// ── Core fetch wrapper ───────────────────────────────────────────────────────

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface StatementSummary {
  id: number;
  original_filename: string;
  status: string;
  extracted_count: number;
  card_type?: string | null;
  labels?: string[] | null;
  notes?: string | null;
  created_at?: string | null;
  created_by_username?: string | null;
}

export interface StatementListResponse {
  statements: StatementSummary[];
  total: number;
}

export interface MergeResponse {
  success: boolean;
  message: string;
  merged_id: number;
  download_url?: string | null;
  download_expires_at?: string | null;
  direct_download_path?: string | null;
}

// ── API methods ───────────────────────────────────────────────────────────────

export const statementToolsApi = {
  listStatements: (params?: {
    skip?: number;
    limit?: number;
    status?: string;
    search?: string;
    label?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.skip != null) qs.set("skip", String(params.skip));
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.status) qs.set("status", params.status);
    if (params?.search) qs.set("search", params.search);
    if (params?.label) qs.set("label", params.label);
    return request<StatementListResponse>(`${PREFIX}/statements?${qs}`);
  },

  merge: (ids: number[]) =>
    request<MergeResponse>(`${PREFIX}/statements/merge`, {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),

  downloadUrl: (statementId: number) =>
    `${BASE_URL}${PREFIX}/statements/${statementId}/download`,
};

// ── Setup helpers (standalone only) ──────────────────────────────────────────

export interface SetupConfig {
  apiUrl: string;
  apiKey: string;
}

export function saveSetupConfig(config: SetupConfig): void {
  localStorage.setItem("yfw_api_url", config.apiUrl);
  localStorage.setItem("yfw_api_key", config.apiKey);
}

export function loadSetupConfig(): SetupConfig {
  return {
    apiUrl: localStorage.getItem("yfw_api_url") ?? "",
    apiKey: localStorage.getItem("yfw_api_key") ?? "",
  };
}

export async function testConnection(apiUrl: string, apiKey: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/api/v1/external/me`, {
      headers: { "X-API-Key": apiKey },
    });
    return res.ok;
  } catch {
    return false;
  }
}
