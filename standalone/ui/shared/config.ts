export const BASE_URL =
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_URL) || "";

export const API_PREFIX =
  (typeof import.meta !== "undefined" &&
    (import.meta as any).env?.VITE_STATEMENT_TOOLS_PREFIX) ||
  "/api/v1/external/statement-tools";

export const USE_STANDALONE_SETUP =
  (typeof import.meta !== "undefined" &&
    (import.meta as any).env?.VITE_USE_SETUP === "true") ||
  false;

export const STORAGE_KEYS = {
  apiKey: "yfw_api_key",
  apiUrl: "yfw_api_url",
} as const;
