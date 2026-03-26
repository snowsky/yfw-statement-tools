/**
 * MergeStatementsPage — select 2+ bank statements and merge them.
 *
 * Behavior after merge:
 *  - STORAGE_BACKEND=none  → triggers a direct file download in the browser
 *  - STORAGE_BACKEND=s3|…  → shows a presigned download link with expiry info
 */
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { statementToolsApi, type MergeResponse, type StatementSummary } from "../api";

const MERGEABLE_STATUSES = ["uploaded", "processed", "processing"];

export function MergeStatementsPage() {
  const [statements, setStatements] = useState<StatementSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");

  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [merging, setMerging] = useState(false);
  const [mergeResult, setMergeResult] = useState<MergeResponse | null>(null);
  const [mergeError, setMergeError] = useState("");

  // ── Fetch statements ───────────────────────────────────────────────────────

  useEffect(() => {
    setLoading(true);
    setFetchError("");
    statementToolsApi
      .listStatements({ skip: page * PAGE_SIZE, limit: PAGE_SIZE, search: search || undefined })
      .then((data) => {
        setStatements(data.statements);
        setTotal(data.total);
      })
      .catch((e: Error) => setFetchError(e.message))
      .finally(() => setLoading(false));
  }, [page, search]);

  // ── Selection helpers ──────────────────────────────────────────────────────

  function toggle(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    const mergeableIds = statements
      .filter((s) => MERGEABLE_STATUSES.includes(s.status))
      .map((s) => s.id);
    const allSelected = mergeableIds.every((id) => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set() : new Set(mergeableIds));
  }

  // ── Merge ──────────────────────────────────────────────────────────────────

  async function handleMerge() {
    if (selectedIds.size < 2) return;
    setMerging(true);
    setMergeError("");
    setMergeResult(null);

    try {
      const result = await statementToolsApi.merge([...selectedIds]);
      setMergeResult(result);
      setSelectedIds(new Set());

      // Direct download: create a hidden <a> and click it
      if (result.direct_download_path) {
        const a = document.createElement("a");
        a.href = statementToolsApi.downloadUrl(result.merged_id);
        a.download = `merged-statement-${result.merged_id}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }

      // Refresh list to show new merged statement
      const refreshed = await statementToolsApi.listStatements({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        search: search || undefined,
      });
      setStatements(refreshed.statements);
      setTotal(refreshed.total);
    } catch (e: unknown) {
      setMergeError((e as Error).message);
    } finally {
      setMerging(false);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const mergeableSelected = [...selectedIds].every((id) =>
    statements.find((s) => s.id === id && MERGEABLE_STATUSES.includes(s.status))
  );
  const canMerge = selectedIds.size >= 2 && mergeableSelected;

  return (
    <div style={pageStyle}>
      <h1 style={headingStyle}>Merge Statements</h1>
      <p style={subtitleStyle}>
        Select two or more statements to merge into a single consolidated file.
      </p>

      {/* Search + action bar */}
      <div style={toolbarStyle}>
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          placeholder="Search by filename…"
          style={{ ...inputStyle, flex: 1 }}
        />
        <button
          onClick={handleMerge}
          disabled={!canMerge || merging}
          style={canMerge && !merging ? btnPrimary : btnDisabled}
        >
          {merging ? "Merging…" : `Merge ${selectedIds.size > 0 ? `(${selectedIds.size})` : ""}`}
        </button>
      </div>

      {/* Errors */}
      {fetchError && <div style={errorBox}>{fetchError}</div>}
      {mergeError && <div style={errorBox}>{mergeError}</div>}

      {/* Merge result */}
      {mergeResult && (
        <div style={successBox}>
          <strong>{mergeResult.message}</strong>
          {mergeResult.download_url && (
            <div style={{ marginTop: 8 }}>
              <a href={mergeResult.download_url} target="_blank" rel="noreferrer" style={linkStyle}>
                Download merged file
              </a>
              {mergeResult.download_expires_at && (
                <span style={{ fontSize: 12, color: "#555", marginLeft: 8 }}>
                  (expires {new Date(mergeResult.download_expires_at).toLocaleDateString()})
                </span>
              )}
            </div>
          )}
          {mergeResult.direct_download_path && (
            <p style={{ fontSize: 13, marginTop: 6, color: "#555" }}>
              File download started automatically.
            </p>
          )}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <p style={{ color: "#888", marginTop: 24 }}>Loading statements…</p>
      ) : (
        <div style={{ overflowX: "auto", marginTop: 16 }}>
          <table style={tableStyle}>
            <thead>
              <tr style={theadRowStyle}>
                <th style={thStyle}>
                  <input type="checkbox" onChange={toggleAll} />
                </th>
                <th style={thStyle}>Filename</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Type</th>
                <th style={thStyle}>Transactions</th>
                <th style={thStyle}>Created</th>
              </tr>
            </thead>
            <tbody>
              {statements.map((s) => {
                const mergeable = MERGEABLE_STATUSES.includes(s.status);
                const checked = selectedIds.has(s.id);
                return (
                  <tr
                    key={s.id}
                    style={{
                      ...trStyle,
                      background: checked ? "#eff6ff" : undefined,
                      opacity: mergeable ? 1 : 0.45,
                    }}
                    onClick={() => mergeable && toggle(s.id)}
                  >
                    <td style={tdStyle}>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={!mergeable}
                        onChange={() => toggle(s.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td style={{ ...tdStyle, maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.original_filename}
                    </td>
                    <td style={tdStyle}>
                      <span style={{ ...badge, ...statusColor(s.status) }}>{s.status}</span>
                    </td>
                    <td style={tdStyle}>{s.card_type ?? "—"}</td>
                    <td style={{ ...tdStyle, textAlign: "right" }}>{s.extracted_count}</td>
                    <td style={tdStyle}>
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                );
              })}
              {statements.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ ...tdStyle, textAlign: "center", color: "#888", padding: 32 }}>
                    No statements found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div style={paginationStyle}>
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} style={btnOutline}>
            ← Prev
          </button>
          <span style={{ fontSize: 13, color: "#555" }}>
            Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={(page + 1) * PAGE_SIZE >= total}
            style={btnOutline}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function statusColor(status: string): CSSProperties {
  const map: Record<string, CSSProperties> = {
    processed: { background: "#dcfce7", color: "#166534" },
    uploaded: { background: "#dbeafe", color: "#1e40af" },
    processing: { background: "#fef9c3", color: "#854d0e" },
    failed: { background: "#fee2e2", color: "#991b1b" },
    merged: { background: "#f3f4f6", color: "#374151" },
  };
  return map[status] ?? { background: "#f3f4f6", color: "#374151" };
}

// ── Styles ─────────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = { maxWidth: 900, margin: "32px auto", fontFamily: "sans-serif", padding: "0 16px" };
const headingStyle: CSSProperties = { fontSize: 22, fontWeight: 700, marginBottom: 6 };
const subtitleStyle: CSSProperties = { color: "#666", fontSize: 14, marginBottom: 20 };
const toolbarStyle: CSSProperties = { display: "flex", gap: 10, marginBottom: 12, alignItems: "center" };
const inputStyle: CSSProperties = { padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14, outline: "none" };
const btnPrimary: CSSProperties = { padding: "8px 20px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14, fontWeight: 600, whiteSpace: "nowrap" };
const btnDisabled: CSSProperties = { ...btnPrimary, background: "#93c5fd", cursor: "not-allowed" };
const btnOutline: CSSProperties = { ...btnPrimary, background: "#fff", color: "#374151", border: "1px solid #d1d5db" };
const errorBox: CSSProperties = { background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "12px 16px", color: "#991b1b", marginBottom: 12, fontSize: 14 };
const successBox: CSSProperties = { background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: "12px 16px", marginBottom: 12, fontSize: 14 };
const linkStyle: CSSProperties = { color: "#2563eb", fontWeight: 500 };
const tableStyle: CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 13 };
const theadRowStyle: CSSProperties = { background: "#f9fafb" };
const thStyle: CSSProperties = { padding: "10px 12px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #e5e7eb", whiteSpace: "nowrap" };
const trStyle: CSSProperties = { cursor: "pointer", borderBottom: "1px solid #f3f4f6" };
const tdStyle: CSSProperties = { padding: "10px 12px" };
const badge: CSSProperties = { display: "inline-block", padding: "2px 8px", borderRadius: 12, fontSize: 11, fontWeight: 600 };
const paginationStyle: CSSProperties = { display: "flex", gap: 12, alignItems: "center", justifyContent: "center", marginTop: 20 };
