/**
 * UploadStatementsPage — upload bank statement files (CSV or PDF).
 *
 * Three modes:
 *   - "Local CSV"        → parse locally, download merged CSV (text-based CSVs)
 *   - "YFW AI"           → forward to YFW's OCR+AI processor, download CSV
 *                          (works for image-rendered PDFs like Scotiabank)
 *   - "Create in YFW"    → push parsed transactions to YFW External Transactions
 *                          (requires commercial license)
 */
import { useRef, useState } from "react";
import type { CSSProperties, DragEvent } from "react";
import { statementToolsApi, type MergeResponse, type UploadToYFWResponse } from "../api";

type Mode = "csv" | "ai" | "yfw";

const ACCEPTED = ".csv,.pdf";
const ACCEPT_TYPES = ["text/csv", "application/pdf", "text/plain"];

function isAccepted(file: File): boolean {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return ext === "csv" || ext === "pdf" || ACCEPT_TYPES.includes(file.type);
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const MODES: { id: Mode; label: string; hint: string }[] = [
  {
    id: "csv",
    label: "Local CSV",
    hint: "Parse locally and download a merged CSV. Best for text-based CSV exports from your bank.",
  },
  {
    id: "ai",
    label: "YFW AI",
    hint: "Forward each file to YFW's OCR + AI processor. Works for image-rendered PDFs (e.g. Scotiabank, TD, RBC e-statements). Only available as a YFW plugin — not in standalone mode.",
  },
  {
    id: "yfw",
    label: "Create in YFW",
    hint: "Parse locally and push transactions to YFW's External Transactions for review. Requires commercial license.",
  },
];

export function UploadStatementsPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState<Mode>("csv");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [csvResult, setCsvResult] = useState<MergeResponse | null>(null);
  const [yfwResult, setYfwResult] = useState<UploadToYFWResponse | null>(null);
  const [aiDone, setAiDone] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    const accepted = Array.from(incoming).filter(isAccepted);
    const rejected = Array.from(incoming).length - accepted.length;
    if (rejected > 0) setError(`${rejected} file(s) skipped — only CSV and PDF are supported.`);
    else setError("");
    setFiles((prev: File[]) => {
      const names = new Set(prev.map((f: File) => f.name));
      return [...prev, ...accepted.filter((f: File) => !names.has(f.name))];
    });
  }

  function removeFile(name: string) {
    setFiles((prev: File[]) => prev.filter((f: File) => f.name !== name));
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  function switchMode(m: Mode) {
    setMode(m);
    setCsvResult(null);
    setYfwResult(null);
    setAiDone(false);
    setError("");
  }

  async function handleUpload() {
    if (files.length === 0) return;
    setUploading(true);
    setError("");
    setCsvResult(null);
    setYfwResult(null);
    setAiDone(false);

    try {
      if (mode === "csv") {
        const res = await statementToolsApi.upload(files);
        setCsvResult(res);
        setFiles([]);
      } else if (mode === "ai") {
        // Process each file individually through YFW AI
        for (const f of files) {
          await statementToolsApi.processWithYfw(f);
        }
        setAiDone(true);
        setFiles([]);
      } else {
        const res = await statementToolsApi.uploadToYfw(files);
        setYfwResult(res);
        setFiles([]);
      }
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  const canSubmit = files.length > 0 && !uploading;
  const currentMode = MODES.find((m) => m.id === mode)!;

  function buttonLabel(): string {
    if (uploading) {
      if (mode === "csv") return "Parsing…";
      if (mode === "ai") return "Processing with YFW AI…";
      return "Uploading to YFW…";
    }
    if (files.length === 0) return "Select files above";
    const n = files.length;
    const s = n > 1 ? `s` : "";
    if (mode === "csv") return `Parse & Download (${n} file${s})`;
    if (mode === "ai") return `Process with YFW AI (${n} file${s})`;
    return `Create in YFW (${n} file${s})`;
  }

  return (
    <div style={pageStyle}>
      {/* Header */}
      <div style={headerRowStyle}>
        <div>
          <h1 style={headingStyle}>Upload Statements</h1>
          <p style={subtitleStyle}>
            Upload CSV or PDF bank statements.
          </p>
        </div>
        <a href="/merge" style={navLinkStyle}>← Merge from YFW</a>
      </div>

      {/* Mode tabs */}
      <div style={modeRowStyle}>
        {MODES.map((m) => (
          <button key={m.id} onClick={() => switchMode(m.id)} style={mode === m.id ? modeTabActive : modeTab}>
            {m.label}
          </button>
        ))}
      </div>
      <p style={modeHintStyle}>{currentMode.hint}</p>

      {/* Drop zone */}
      <div
        style={{ ...dropZoneStyle, ...(dragging ? dropZoneActiveStyle : {}) }}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED}
          style={{ display: "none" }}
          onChange={(e) => addFiles(e.target.files)}
        />
        <div style={dropIconStyle}>↑</div>
        <div style={{ fontSize: 14, color: "#374151", fontWeight: 500 }}>
          {dragging ? "Drop files here" : "Click or drag & drop CSV / PDF files"}
        </div>
        {mode === "ai" && (
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
            One file processed at a time — each downloads separately
          </div>
        )}
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div style={fileListStyle}>
          {files.map((f: File) => (
            <div key={f.name} style={fileRowStyle}>
              <span style={fileIconStyle}>{f.name.endsWith(".pdf") ? "📄" : "📊"}</span>
              <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {f.name}
              </span>
              <span style={{ fontSize: 12, color: "#9ca3af", marginRight: 12 }}>{formatBytes(f.size)}</span>
              <button onClick={() => removeFile(f.name)} style={removeBtnStyle}>✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div style={actionsStyle}>
        <button onClick={handleUpload} disabled={!canSubmit} style={canSubmit ? btnPrimary : btnDisabled}>
          {buttonLabel()}
        </button>
        {files.length > 0 && (
          <button onClick={() => setFiles([])} style={btnOutline}>Clear all</button>
        )}
      </div>

      {/* Error */}
      {error && <div style={errorBox}>{error}</div>}

      {/* AI result */}
      {aiDone && (
        <div style={successBox}>
          <strong>Download started.</strong>
          <span style={{ marginLeft: 8, fontSize: 13, color: "#555" }}>
            YFW AI extracted and saved the transactions.
          </span>
        </div>
      )}

      {/* Local CSV result */}
      {csvResult && (
        <div style={successBox}>
          <strong>{csvResult.message}</strong>
          {csvResult.transaction_count > 0 && (
            <span style={{ marginLeft: 8, color: "#555", fontSize: 13 }}>
              ({csvResult.transaction_count} transactions)
            </span>
          )}
          {csvResult.download_url && (
            <div style={{ marginTop: 8 }}>
              <a href={csvResult.download_url} target="_blank" rel="noreferrer" style={linkStyle}>
                Download merged CSV
              </a>
              {csvResult.download_expires_at && (
                <span style={{ fontSize: 12, color: "#555", marginLeft: 8 }}>
                  (expires {new Date(csvResult.download_expires_at).toLocaleDateString()})
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* YFW External Transactions result */}
      {yfwResult && (
        <div style={yfwResult.success ? successBox : errorBox}>
          <strong>{yfwResult.message}</strong>
          <div style={{ marginTop: 6, fontSize: 13 }}>
            <span style={statPill}>✓ {yfwResult.created_count} created</span>
            {yfwResult.failed_count > 0 && (
              <span style={{ ...statPill, background: "#fee2e2", color: "#991b1b" }}>
                ✕ {yfwResult.failed_count} failed
              </span>
            )}
          </div>
          {yfwResult.errors.length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary style={{ fontSize: 12, cursor: "pointer", color: "#6b7280" }}>
                Show errors ({yfwResult.errors.length})
              </summary>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12, color: "#6b7280" }}>
                {yfwResult.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Format hints */}
      <div style={hintsStyle}>
        <strong style={{ fontSize: 13 }}>Which mode to use?</strong>
        <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13, color: "#6b7280" }}>
          <li><strong>Local CSV</strong> — text-based CSV exports from your bank portal</li>
          <li><strong>YFW AI</strong> — PDFs (image-rendered like Scotiabank, TD, RBC) — plugin mode only; use bank's CSV export in standalone</li>
          <li><strong>Create in YFW</strong> — push transactions into YFW for reconciliation (commercial license required)</li>
        </ul>
      </div>
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = { maxWidth: 720, margin: "32px auto", fontFamily: "sans-serif", padding: "0 16px" };
const headerRowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 };
const headingStyle: CSSProperties = { fontSize: 22, fontWeight: 700, marginBottom: 6 };
const subtitleStyle: CSSProperties = { color: "#666", fontSize: 14, margin: 0 };
const navLinkStyle: CSSProperties = { fontSize: 13, color: "#2563eb", textDecoration: "none", whiteSpace: "nowrap", marginTop: 4 };

const modeRowStyle: CSSProperties = { display: "flex", gap: 0, marginBottom: 8, border: "1px solid #d1d5db", borderRadius: 8, overflow: "hidden", width: "fit-content" };
const modeTab: CSSProperties = { padding: "8px 18px", background: "#fff", color: "#374151", border: "none", borderRight: "1px solid #d1d5db", cursor: "pointer", fontSize: 14, fontWeight: 500 };
const modeTabActive: CSSProperties = { ...modeTab, background: "#2563eb", color: "#fff" };
const modeHintStyle: CSSProperties = { fontSize: 12, color: "#6b7280", marginBottom: 16, marginTop: 0, maxWidth: 600 };

const dropZoneStyle: CSSProperties = {
  border: "2px dashed #d1d5db", borderRadius: 12, padding: "36px 24px",
  textAlign: "center", cursor: "pointer", background: "#f9fafb",
};
const dropZoneActiveStyle: CSSProperties = { borderColor: "#2563eb", background: "#eff6ff" };
const dropIconStyle: CSSProperties = { fontSize: 28, marginBottom: 6, color: "#9ca3af" };

const fileListStyle: CSSProperties = { marginTop: 12, border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" };
const fileRowStyle: CSSProperties = { display: "flex", alignItems: "center", padding: "10px 14px", borderBottom: "1px solid #f3f4f6", background: "#fff" };
const fileIconStyle: CSSProperties = { marginRight: 10, fontSize: 16 };
const removeBtnStyle: CSSProperties = { background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: 14, padding: "2px 4px" };

const actionsStyle: CSSProperties = { display: "flex", gap: 10, marginTop: 14 };
const btnPrimary: CSSProperties = { padding: "9px 22px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14, fontWeight: 600 };
const btnDisabled: CSSProperties = { ...btnPrimary, background: "#93c5fd", cursor: "not-allowed" };
const btnOutline: CSSProperties = { ...btnPrimary, background: "#fff", color: "#374151", border: "1px solid #d1d5db" };

const errorBox: CSSProperties = { background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "12px 16px", color: "#991b1b", marginTop: 14, fontSize: 14 };
const successBox: CSSProperties = { background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: "12px 16px", marginTop: 14, fontSize: 14 };
const linkStyle: CSSProperties = { color: "#2563eb", fontWeight: 500 };
const statPill: CSSProperties = { display: "inline-block", padding: "2px 10px", background: "#dcfce7", color: "#166534", borderRadius: 12, fontSize: 12, marginRight: 6, fontWeight: 500 };
const hintsStyle: CSSProperties = { marginTop: 24, padding: "14px 18px", background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8 };
