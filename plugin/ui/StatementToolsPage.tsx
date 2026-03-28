/**
 * Statement Tools — plugin page for YourFinanceWORKS.
 *
 * Self-contained: no imports from shared/ so it survives being copied to
 * ui/src/plugins/statement_tools/ by the YFW plugin installer.
 *
 * API calls target the plugin's own backend routes (same origin):
 *   POST /api/v1/statement-tools/batch/upload
 *   GET  /api/v1/statement-tools/batch/jobs/{job_id}
 */
import { useRef, useState, useEffect } from "react";
import type { CSSProperties, DragEvent } from "react";

// ── Constants ────────────────────────────────────────────────────────────────

const API_PREFIX = "/api/v1/statement-tools";
const ACCEPTED = ".csv,.pdf";
const ACCEPT_TYPES = ["text/csv", "application/pdf"];
const MAX_FILE_SIZE = 20 * 1024 * 1024;

// ── Types ────────────────────────────────────────────────────────────────────

interface BatchUploadResponse {
  success: boolean;
  job_id: string;
  status: string;
  message?: string;
}

interface BatchFileStatus {
  id: number;
  filename: string;
  status: string;
  error_message?: string;
  extracted_data?: { transactions?: Transaction[] };
}

interface BatchJobStatus {
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

interface Transaction {
  date?: string;
  description?: string;
  amount?: number | string;
  transaction_type?: string;
  category?: string;
  balance?: number | string;
  source_file?: string;
  [key: string]: unknown;
}

// ── API ──────────────────────────────────────────────────────────────────────

async function uploadBatch(files: File[]): Promise<BatchUploadResponse> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(`${API_PREFIX}/batch/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

async function getJobStatus(jobId: string): Promise<BatchJobStatus> {
  const res = await fetch(`${API_PREFIX}/batch/jobs/${jobId}`);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── CSV export ───────────────────────────────────────────────────────────────

function buildCsv(files: BatchFileStatus[]): string {
  const headers = ["date", "description", "amount", "transaction_type", "category", "balance", "source_file"];
  const rows: Transaction[] = [];

  for (const file of files) {
    for (const tx of file.extracted_data?.transactions ?? []) {
      rows.push({ ...tx, source_file: file.filename });
    }
  }

  rows.sort((a, b) => String(a.date ?? "").localeCompare(String(b.date ?? "")));

  const escape = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [headers.join(","), ...rows.map(r => headers.map(h => escape(r[h])).join(","))].join("\n");
}

function downloadCsv(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function isAccepted(file: File): boolean {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return ext === "csv" || ext === "pdf" || ACCEPT_TYPES.includes(file.type);
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const TERMINAL = new Set(["completed", "failed", "partial_failure"]);

// ── Component ────────────────────────────────────────────────────────────────

export default function StatementToolsPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<BatchJobStatus | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Poll until terminal state
  useEffect(() => {
    if (!jobId || !job || TERMINAL.has(job.status)) return;
    const id = window.setInterval(async () => {
      try {
        const s = await getJobStatus(jobId);
        setJob(s);
        if (TERMINAL.has(s.status)) clearInterval(id);
      } catch (e) {
        console.error("Poll error:", e);
      }
    }, 3000);
    return () => clearInterval(id);
  }, [jobId, job?.status]);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const accepted: File[] = [];
    let skipped = 0;
    for (const f of Array.from(list)) {
      if (!isAccepted(f)) { skipped++; continue; }
      if (f.size > MAX_FILE_SIZE) { skipped++; continue; }
      accepted.push(f);
    }
    if (skipped > 0) setError(`${skipped} file(s) skipped — only CSV/PDF up to 20 MB accepted.`);
    else setError("");
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...accepted.filter(f => !names.has(f.name))];
    });
  }

  async function handleUpload() {
    if (!files.length) return;
    setUploading(true);
    setError("");
    setJob(null);
    setJobId(null);
    try {
      const res = await uploadBatch(files);
      setJobId(res.job_id);
      setJob({ job_id: res.job_id, status: res.status, processed_files: 0, total_files: files.length, successful_files: 0, failed_files: 0, progress_percentage: 0, files: [] });
      setFiles([]);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  function handleDownload() {
    if (!job) return;
    const csv = buildCsv(job.files);
    downloadCsv(csv, `statements-${new Date().toISOString().slice(0, 10)}.csv`);
  }

  const isDone = job && TERMINAL.has(job.status);
  const isProcessing = jobId && job && !TERMINAL.has(job.status);
  const canUpload = files.length > 0 && !uploading && !jobId;

  return (
    <div style={s.page}>
      <h1 style={s.heading}>Statement Tools</h1>
      <p style={s.subtitle}>
        Upload CSV or PDF bank statements — AI extracts and merges all transactions into a single download.
      </p>

      {/* Drop zone */}
      {!jobId && (
        <div
          style={{ ...s.dropZone, ...(dragging ? s.dropZoneActive : {}) }}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e: DragEvent<HTMLDivElement>) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e: DragEvent<HTMLDivElement>) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        >
          <input ref={inputRef} type="file" multiple accept={ACCEPTED} style={{ display: "none" }}
            onChange={e => addFiles(e.target.files)} />
          <div style={s.dropIcon}>↑</div>
          <div style={{ fontSize: 14, color: "#374151", fontWeight: 500 }}>
            {dragging ? "Drop files here" : "Click or drag & drop CSV / PDF files"}
          </div>
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
            Bulk upload supported — up to 20 MB per file
          </div>
        </div>
      )}

      {/* Queued file list */}
      {!jobId && files.length > 0 && (
        <div style={s.fileList}>
          {files.map(f => (
            <div key={f.name} style={s.fileRow}>
              <span style={s.fileIcon}>{f.name.endsWith(".pdf") ? "📄" : "📊"}</span>
              <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
              <span style={{ fontSize: 12, color: "#9ca3af", marginRight: 12 }}>{formatBytes(f.size)}</span>
              <button onClick={() => setFiles(prev => prev.filter(x => x.name !== f.name))} style={s.removeBtn}>✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Job progress */}
      {job && (
        <div style={s.jobBox}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>Job {job.job_id.slice(0, 8)}…</span>
            <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 12, background: isDone ? "#dcfce7" : "#fef9c3", color: isDone ? "#166534" : "#854d0e" }}>
              {job.status.toUpperCase()}
            </span>
          </div>
          <div style={s.progressBg}>
            <div style={{ ...s.progressFill, width: `${job.progress_percentage}%`, background: job.status === "failed" ? "#ef4444" : "#2563eb" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 12, color: "#6b7280" }}>
            <span>{job.processed_files} of {job.total_files} files</span>
            <span>{Math.round(job.progress_percentage)}%</span>
          </div>

          {job.files.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ fontSize: 12, cursor: "pointer", color: "#374151" }}>File details</summary>
              <div style={{ maxHeight: 200, overflowY: "auto", marginTop: 8, fontSize: 12 }}>
                {job.files.map(f => (
                  <div key={f.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #f3f4f6" }}>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{f.filename}</span>
                    <span style={{ color: f.status === "completed" ? "#166534" : f.status === "failed" ? "#991b1b" : "#6b7280", fontWeight: 500 }}>{f.status}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {/* Actions */}
      <div style={s.actions}>
        {!jobId ? (
          <>
            <button onClick={handleUpload} disabled={!canUpload} style={canUpload ? s.btnPrimary : s.btnDisabled}>
              {uploading ? "Starting…" : `Upload & Process${files.length > 0 ? ` (${files.length})` : ""}`}
            </button>
            {files.length > 0 && (
              <button onClick={() => setFiles([])} style={s.btnOutline}>Clear all</button>
            )}
          </>
        ) : (
          <>
            {isDone && (
              <button onClick={handleDownload} style={s.btnPrimary}>⬇ Download Merged CSV</button>
            )}
            <button onClick={() => { setJobId(null); setJob(null); }} style={s.btnOutline}>
              {isProcessing ? "Processing…" : "New Upload"}
            </button>
          </>
        )}
      </div>

      {error && <div style={s.error}>{error}</div>}
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const s: Record<string, CSSProperties> = {
  page:       { maxWidth: 720, margin: "32px auto", fontFamily: "sans-serif", padding: "0 16px" },
  heading:    { fontSize: 22, fontWeight: 700, marginBottom: 6 },
  subtitle:   { color: "#666", fontSize: 14, marginBottom: 20 },
  dropZone:   { border: "2px dashed #d1d5db", borderRadius: 12, padding: "36px 24px", textAlign: "center", cursor: "pointer", background: "#f9fafb" },
  dropZoneActive: { borderColor: "#2563eb", background: "#eff6ff" },
  dropIcon:   { fontSize: 28, marginBottom: 6, color: "#9ca3af" },
  fileList:   { marginTop: 12, border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" },
  fileRow:    { display: "flex", alignItems: "center", padding: "10px 14px", borderBottom: "1px solid #f3f4f6", background: "#fff" },
  fileIcon:   { marginRight: 10, fontSize: 16 },
  removeBtn:  { background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: 14, padding: "2px 4px" },
  jobBox:     { marginTop: 20, padding: 16, border: "1px solid #e5e7eb", borderRadius: 12, background: "#fff" },
  progressBg: { height: 8, background: "#e5e7eb", borderRadius: 4, overflow: "hidden" },
  progressFill: { height: "100%", transition: "width 0.3s ease", borderRadius: 4 },
  actions:    { display: "flex", gap: 10, marginTop: 14 },
  btnPrimary: { padding: "9px 22px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14, fontWeight: 600 },
  btnDisabled: { padding: "9px 22px", background: "#e5e7eb", color: "#9ca3af", border: "none", borderRadius: 6, cursor: "not-allowed", fontSize: 14, fontWeight: 600 },
  btnOutline: { padding: "9px 22px", background: "#fff", color: "#374151", border: "1px solid #d1d5db", borderRadius: 6, cursor: "pointer", fontSize: 14, fontWeight: 600 },
  error:      { background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "12px 16px", color: "#991b1b", marginTop: 14, fontSize: 14 },
};
