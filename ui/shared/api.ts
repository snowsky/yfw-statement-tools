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
  const url = localStorage.getItem("yfw_api_url");
  return {
    ...(key ? { "X-API-Key": key } : {}),
    ...(url ? { "X-YFW-URL": url } : {}),
  };
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
  account_name: string;        // original filename from YFW
  statement_date: string;
  total_transactions: number;
}

export interface StatementListResponse {
  statements: StatementSummary[];
  total: number;
}

export interface MergeResponse {
  success: boolean;
  message: string;
  transaction_count: number;
  download_url?: string | null;
  download_expires_at?: string | null;
}

export interface UploadToYFWResponse {
  success: boolean;
  message: string;
  created_count: number;
  failed_count: number;
  errors: string[];
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

  merge: async (ids: number[]): Promise<MergeResponse> => {
    const res = await fetch(`${BASE_URL}${PREFIX}/statements/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? `HTTP ${res.status}`);
    }
    const ct = res.headers.get("Content-Type") ?? "";
    if (ct.includes("text/csv")) {
      // Stateless mode: trigger browser download
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="([^"]+)"/);
      a.href = url;
      a.download = match?.[1] ?? "merged-statements.csv";
      a.click();
      URL.revokeObjectURL(url);
      return { success: true, message: "Download started.", transaction_count: 0 };
    }
    return res.json() as Promise<MergeResponse>;
  },

  downloadUrl: (statementId: number) =>
    `${BASE_URL}${PREFIX}/statements/${statementId}/download`,

  upload: async (files: File[]): Promise<MergeResponse> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);

    const res = await fetch(`${BASE_URL}${PREFIX}/statements/upload`, {
      method: "POST",
      headers: authHeaders(),  // no Content-Type — browser sets multipart boundary
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? `HTTP ${res.status}`);
    }
    const ct = res.headers.get("Content-Type") ?? "";
    if (ct.includes("text/csv")) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="([^"]+)"/);
      a.href = url;
      a.download = match?.[1] ?? "uploaded-statements.csv";
      a.click();
      URL.revokeObjectURL(url);
      return { success: true, message: "Download started.", transaction_count: 0 };
    }
    return res.json() as Promise<MergeResponse>;
  },

  processWithYfw: async (file: File): Promise<void> => {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${BASE_URL}${PREFIX}/statements/process-with-yfw`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail?.detail ?? `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const disposition = res.headers.get("Content-Disposition") ?? "";
    const match = disposition.match(/filename="([^"]+)"/);
    a.href = url;
    a.download = match?.[1] ?? `${file.name.replace(/\.pdf$/i, "")}-transactions.csv`;
    a.click();
    URL.revokeObjectURL(url);
  },

  uploadToYfw: async (files: File[], sourceSystem = "statement-tools"): Promise<UploadToYFWResponse> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    form.append("source_system", sourceSystem);

    const res = await fetch(
      `${BASE_URL}${PREFIX}/statements/upload-to-yfw`,
      { method: "POST", headers: authHeaders(), body: form }
    );
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      if (res.status === 402) {
        throw new Error(
          "The External Transactions feature is not enabled on your YFW instance. " +
          "It requires a commercial license. During a trial period it is available automatically."
        );
      }
      if (res.status === 403) {
        throw new Error(
          "Your API key does not have External Transactions write permission. " +
          "Check your API client settings in YFW."
        );
      }
      throw new Error(detail?.detail ?? `HTTP ${res.status}`);
    }
    return res.json() as Promise<UploadToYFWResponse>;
  },
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

/** Test connectivity via the standalone backend (avoids browser CORS issues). */
export async function testConnection(
  apiUrl: string,
  apiKey: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(`${BASE_URL}/api/v1/statement-tools/check-connection`, {
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
