import React, { useRef, useState, useEffect } from "react";
import type { CSSProperties, DragEvent } from "react";
import { statementToolsApi, type BatchJobStatus } from "../api";
import { generateMergedCSV, downloadBlob } from "../utils/csv-export";

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

export function UploadStatementsPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<BatchJobStatus | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Poll for job status
  useEffect(() => {
    let interval: number | undefined;

    if (activeJobId && !jobStatus?.completed_at && jobStatus?.status !== "failed" && jobStatus?.status !== "completed") {
      interval = window.setInterval(async () => {
        try {
          const status = await statementToolsApi.getJobStatus(activeJobId);
          setJobStatus(status);
          
          if (status.status === "completed" || status.status === "failed" || status.status === "partial_failure") {
            window.clearInterval(interval);
          }
        } catch (e) {
          console.error("Polling error:", e);
        }
      }, 3000);
    }

    return () => window.clearInterval(interval);
  }, [activeJobId, jobStatus?.status, jobStatus?.completed_at]);

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

  async function handleUpload() {
    if (files.length === 0) return;
    setUploading(true);
    setError("");
    setJobStatus(null);
    setActiveJobId(null);

    try {
      const res = await statementToolsApi.uploadBatch(files);
      setActiveJobId(res.job_id);
      // Initialize status
      setJobStatus({
        job_id: res.job_id,
        status: res.status,
        processed_files: 0,
        total_files: files.length,
        successful_files: 0,
        failed_files: 0,
        progress_percentage: 0,
        files: []
      });
      setFiles([]);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  function handleDownload() {
    if (!jobStatus) return;
    const csvContent = generateMergedCSV(jobStatus.files);
    downloadBlob(csvContent, `merged-statements-${new Date().toISOString().slice(0, 10)}.csv`, "text/csv");
  }

  const canSubmit = files.length > 0 && !uploading && !activeJobId;
  const isProcessing = activeJobId && jobStatus && jobStatus.status !== "completed" && jobStatus.status !== "failed";
  const isDone = jobStatus && (jobStatus.status === "completed" || jobStatus.status === "partial_failure");

  return (
    <div style={pageStyle}>
      <h1 style={headingStyle}>Upload Statements</h1>
      <p style={subtitleStyle}>
        Asynchronously upload and process bank statements. Results are merged into a single CSV for download.
      </p>

      {/* Drop zone */}
      {!activeJobId && (
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
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
            Bulk upload supported — monitor progress as AI parses each file
          </div>
        </div>
      )}

      {/* File list (pre-upload) */}
      {!activeJobId && files.length > 0 && (
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

      {/* Active Job Progress */}
      {jobStatus && (
        <div style={jobContainerStyle}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>
              Job: {jobStatus.job_id.slice(0, 8)}...
            </span>
            <span style={{ 
              fontSize: 12, 
              padding: "2px 8px", 
              borderRadius: 12, 
              background: jobStatus.status === "completed" ? "#dcfce7" : "#fef9c3",
              color: jobStatus.status === "completed" ? "#166534" : "#854d0e"
            }}>
              {jobStatus.status.toUpperCase()}
            </span>
          </div>

          <div style={progressBgStyle}>
            <div style={{ 
              ...progressFillStyle, 
              width: `${jobStatus.progress_percentage}%`,
              background: jobStatus.status === "failed" ? "#ef4444" : "#2563eb"
            }} />
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 12, color: "#6b7280" }}>
            <span>{jobStatus.processed_files} of {jobStatus.total_files} files processed</span>
            <span>{Math.round(jobStatus.progress_percentage)}%</span>
          </div>

          {/* Individual file status inside the job */}
          <details style={{ marginTop: 12 }}>
            <summary style={{ fontSize: 12, cursor: "pointer", color: "#374151" }}>View file details</summary>
            <div style={{ maxHeight: 200, overflowY: "auto", marginTop: 8, fontSize: 12 }}>
              {jobStatus.files.map((f: any) => (
                <div key={f.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #f3f4f6" }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{f.filename}</span>
                  <span style={{ 
                    color: f.status === "completed" ? "#166534" : (f.status === "failed" ? "#991b1b" : "#6b7280"),
                    fontWeight: 500
                  }}>
                    {f.status}
                  </span>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}

      {/* Actions */}
      <div style={actionsStyle}>
        {!activeJobId ? (
          <>
            <button onClick={handleUpload} disabled={!canSubmit} style={canSubmit ? btnPrimary : btnDisabled}>
              {uploading ? "Starting Job..." : `Upload & Process ${files.length > 0 ? `(${files.length} files)` : ""}`}
            </button>
            {files.length > 0 && (
              <button onClick={() => setFiles([])} style={btnOutline}>Clear all</button>
            )}
          </>
        ) : (
          <>
            {isDone && (
              <button onClick={handleDownload} style={btnPrimary}>
                ⬇ Download Merged CSV
              </button>
            )}
            <button 
              onClick={() => { setActiveJobId(null); setJobStatus(null); }} 
              style={btnOutline}
            >
              Start New Job
            </button>
          </>
        )}
      </div>

      {/* Error */}
      {error && <div style={errorBox}>{error}</div>}
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = { maxWidth: 720, margin: "32px auto", fontFamily: "sans-serif", padding: "0 16px" };
const headingStyle: CSSProperties = { fontSize: 22, fontWeight: 700, marginBottom: 6 };
const subtitleStyle: CSSProperties = { color: "#666", fontSize: 14, marginBottom: 20 };

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

const jobContainerStyle: CSSProperties = { marginTop: 20, padding: 16, border: "1px solid #e5e7eb", borderRadius: 12, background: "#fff" };
const progressBgStyle: CSSProperties = { height: 8, background: "#e5e7eb", borderRadius: 4, overflow: "hidden" };
const progressFillStyle: CSSProperties = { height: "100%", transition: "width 0.3s ease", borderRadius: 4 };

const actionsStyle: CSSProperties = { display: "flex", gap: 10, marginTop: 14 };
const btnPrimary: CSSProperties = { padding: "9px 22px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14, fontWeight: 600 };
const btnDisabled: CSSProperties = { ...btnPrimary, background: "#e5e7eb", color: "#9ca3af", cursor: "not-allowed" };
const btnOutline: CSSProperties = { ...btnPrimary, background: "#fff", color: "#374151", border: "1px solid #d1d5db" };

const errorBox: CSSProperties = { background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "12px 16px", color: "#991b1b", marginTop: 14, fontSize: 14 };
