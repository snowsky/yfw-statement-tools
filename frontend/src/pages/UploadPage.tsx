import React, { useRef, useState, useEffect } from 'react'
import type { CSSProperties, DragEvent, ChangeEvent } from 'react'
import { statementsApi } from '@/api/statements'
import { apiRequest } from '@/lib/api/_base'
import { getVisitorId, getPublicTenantId } from '@/lib/visitor'
import { recordPublicUsage } from '@/lib/publicUsage'
import type { BatchFileStatus, BatchJobStatus } from '@/types'

const isSidecar = import.meta.env.VITE_MODE === 'sidecar'

/** Build a shareable link for the given download token.
 *  Uses the platform's public /p/ routing which now forwards query params. */
function shareUrl(token: string): string {
  const base = window.location.origin
  // Extract tenant ID from current URL if present (t=1)
  const params = new URLSearchParams(window.location.search)
  const tenantId = params.get('t')
  const tParam = tenantId ? `&t=${tenantId}` : ''
  
  return isSidecar
    ? `${base}/p/statement-tools?token=${token}${tParam}`
    : `${base}/statement-tools/public?token=${token}`
}

const ACCEPTED = '.csv,.pdf'

function isAccepted(file: File): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return ext === 'csv' || ext === 'pdf'
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<BatchJobStatus | null>(null)
  const [shareLink, setShareLink] = useState<string | null>(null)
  const [generatingLink, setGeneratingLink] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const [quota, setQuota] = useState<{ remaining: number; daily_limit: number } | null>(null)
  const [showPaywall, setShowPaywall] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const isPublic = !localStorage.getItem('token') && !localStorage.getItem('statement_tools_api_key')

  // Initial quota check for public users
  useEffect(() => {
    if (isPublic) {
      checkPublicQuota()
    }
  }, [isPublic])

  async function checkPublicQuota() {
    try {
      const visitorId = getVisitorId()
      const tenantId = getPublicTenantId()
      if (!visitorId || !tenantId) return

      const data: any = await apiRequest(`/plugins/public-quota/statement-tools?visitor_id=${visitorId}&tenant_id=${tenantId}`)
      setQuota({ remaining: data.remaining, daily_limit: data.daily_limit })
      if (data.remaining <= 0) {
        setShowPaywall(true)
      }
    } catch (e) {
      console.error('Quota check failed:', e)
    }
  }

  async function handleCheckout() {
    try {
      const tenantId = getPublicTenantId()
      const visitorId = getVisitorId()
      const data: any = await apiRequest(`/plugins/public-checkout/statement-tools?tenant_id=${tenantId}`, {
        method: 'POST',
        body: JSON.stringify({ visitor_id: visitorId })
      })
      if (data.url) {
        window.location.href = data.url
      }
    } catch (e) {
      console.error('Checkout failed:', e)
      setError('Unable to start checkout session. Please try again later.')
    }
  }

  // Poll for batch job status
  useEffect(() => {
    let interval: number | undefined
    if (
      activeJobId &&
      jobStatus?.status !== 'completed' &&
      jobStatus?.status !== 'failed' &&
      !jobStatus?.completed_at
    ) {
      interval = window.setInterval(async () => {
        try {
          const status = await statementsApi.getJobStatus(activeJobId)
          setJobStatus(status)
          if (
            status.status === 'completed' ||
            status.status === 'failed' ||
            status.status === 'partial_failure'
          ) {
            window.clearInterval(interval)
          }
        } catch (e) {
          console.error('Polling error:', e)
        }
      }, 3000)
    }
    return () => window.clearInterval(interval)
  }, [activeJobId, jobStatus?.status, jobStatus?.completed_at])

  function addFiles(incoming: FileList | null) {
    if (!incoming) return
    let accepted = Array.from(incoming).filter(isAccepted)
    
    // Public tier: 1MB limit
    if (isPublic) {
      const tooLarge = accepted.filter(f => f.size > 1024 * 1024)
      if (tooLarge.length > 0) {
        setError(`Some files were skipped — daily free-tier limit is 1MB per file. Authenticated users enjoy 20MB limits.`)
        accepted = accepted.filter(f => f.size <= 1024 * 1024)
      } else {
        setError('')
      }
    }

    const rejected = Array.from(incoming).length - accepted.length
    if (rejected > 0 && !error) setError(`${rejected} file(s) skipped — only CSV and PDF are supported.`)
    else if (rejected === 0 && !error) setError('')

    setFiles((prev: File[]) => {
      const names = new Set(prev.map((f: File) => f.name))
      return [...prev, ...accepted.filter((f: File) => !names.has(f.name))]
    })
  }

  function removeFile(name: string) {
    setFiles((prev: File[]) => prev.filter((f: File) => f.name !== name))
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }

  async function handleUpload() {
    if (files.length === 0) return
    setUploading(true)
    setError('')
    setJobStatus(null)
    setActiveJobId(null)

    try {
      const res = await statementsApi.uploadBatch(files)
      setActiveJobId(res.job_id)
      setJobStatus({
        job_id: res.job_id,
        status: res.status,
        processed_files: 0,
        total_files: files.length,
        successful_files: 0,
        failed_files: 0,
        progress_percentage: 0,
        files: [],
      })
      setFiles([])
      
      // Track usage in the host application
      recordPublicUsage('batch/upload', files.length)
      
      if (isPublic && !isSidecar) checkPublicQuota()
    } catch (e: any) {
      if (e.message?.includes('402') || e.message?.toLowerCase().includes('quota')) {
        setShowPaywall(true)
      } else {
        setError(e.message || 'Upload failed.')
      }
    } finally {
      setUploading(false)
    }
  }

  async function handleGetShareLink() {
    if (files.length === 0) return
    setGeneratingLink(true)
    setShareLink(null)
    setError('')
    try {
      const res = await statementsApi.upload(files)
      const token = res.download_url.split('/').pop() ?? ''
      setShareLink(shareUrl(token))
      
      // Track usage in the host application
      recordPublicUsage('share/link', files.length)

      if (isPublic && !isSidecar) checkPublicQuota()
    } catch (e: any) {
      if (e.message?.includes('402') || e.message?.toLowerCase().includes('quota')) {
        setShowPaywall(true)
      } else {
        setError(e.message || 'Upload failed.')
      }
    } finally {
      setGeneratingLink(false)
    }
  }

  async function handleCopy() {
    if (!shareLink) return
    await navigator.clipboard.writeText(shareLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const canSubmit = files.length > 0 && !uploading && !activeJobId
  const isDone =
    jobStatus &&
    (jobStatus.status === 'completed' || jobStatus.status === 'partial_failure')

  return (
    <div style={pageStyle}>
      <h1 style={headingStyle}>Statement Tools</h1>
      <p style={subtitleStyle}>
        Upload bank statements (CSV/PDF), extract transactions via AI, and download a merged CSV.
        {isPublic && quota && (
          <span style={{ marginLeft: 8, color: '#2563eb', fontWeight: 600 }}>
            ({quota.remaining} of {quota.daily_limit} free daily files remaining)
          </span>
        )}
      </p>

      {/* Drop zone */}
      {!activeJobId && (
        <div
          style={{ ...dropZoneStyle, ...(dragging ? dropZoneActiveStyle : {}) }}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e: DragEvent<HTMLDivElement>) => onDrop(e)}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED}
            style={{ display: 'none' }}
            onChange={(e: ChangeEvent<HTMLInputElement>) => addFiles(e.target.files)}
          />
          <div style={dropIconStyle}>↑</div>
          <div style={{ fontSize: 14, color: '#374151', fontWeight: 500 }}>
            {dragging ? 'Drop files here' : 'Click or drag & drop CSV / PDF files'}
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
            Bulk upload supported — AI parses each file asynchronously
          </div>
        </div>
      )}

      {/* File list (pre-upload) */}
      {!activeJobId && files.length > 0 && (
        <div style={fileListStyle}>
          {files.map((f: File) => (
            <div key={f.name} style={fileRowStyle}>
              <span style={fileIconStyle}>{f.name.endsWith('.pdf') ? '📄' : '📊'}</span>
              <span style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {f.name}
              </span>
              <span style={{ fontSize: 12, color: '#9ca3af', marginRight: 12 }}>{formatBytes(f.size)}</span>
              <button onClick={() => removeFile(f.name)} style={removeBtnStyle}>✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Job progress */}
      {jobStatus && (
        <div style={jobContainerStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>
              Job: {jobStatus.job_id.slice(0, 8)}...
            </span>
            <span style={{
              fontSize: 12,
              padding: '2px 8px',
              borderRadius: 12,
              background: jobStatus.status === 'completed' ? '#dcfce7' : '#fef9c3',
              color: jobStatus.status === 'completed' ? '#166534' : '#854d0e',
            }}>
              {jobStatus.status.toUpperCase()}
            </span>
          </div>

          <div style={progressBgStyle}>
            <div style={{
              ...progressFillStyle,
              width: `${jobStatus.progress_percentage}%`,
              background: jobStatus.status === 'failed' ? '#ef4444' : '#2563eb',
            }} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 12, color: '#6b7280' }}>
            <span>{jobStatus.processed_files} of {jobStatus.total_files} files processed</span>
            <span>{Math.round(jobStatus.progress_percentage)}%</span>
          </div>

          <details style={{ marginTop: 12 }}>
            <summary style={{ fontSize: 12, cursor: 'pointer', color: '#374151' }}>View file details</summary>
            <div style={{ maxHeight: 200, overflowY: 'auto', marginTop: 8, fontSize: 12 }}>
              {jobStatus.files.map((f: BatchFileStatus) => (
                <div key={f.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #f3f4f6' }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{f.filename}</span>
                  <span style={{
                    color: f.status === 'completed' ? '#166534' : (f.status === 'failed' ? '#991b1b' : '#6b7280'),
                    fontWeight: 500,
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
              {uploading ? 'Starting Job...' : `Upload & Process${files.length > 0 ? ` (${files.length} files)` : ''}`}
            </button>
            {files.length > 0 && (
              <button
                onClick={handleGetShareLink}
                disabled={!canSubmit || generatingLink}
                style={canSubmit && !generatingLink ? btnOutline : btnDisabled}
                title="Generate a shareable download link (sync upload)"
              >
                {generatingLink ? 'Generating...' : '🔗 Get shareable link'}
              </button>
            )}
            {files.length > 0 && (
              <button onClick={() => { setFiles([]); setShareLink(null) }} style={btnOutline}>Clear all</button>
            )}
          </>
        ) : (
          <>
            {isDone && (
              <button
                onClick={() => { setActiveJobId(null); setJobStatus(null) }}
                style={btnOutline}
              >
                Start New Job
              </button>
            )}
          </>
        )}
      </div>

      {/* Shareable link */}
      {shareLink && (
        <div style={shareLinkBox}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: '#1d4ed8' }}>
            Shareable download link (expires in 1 hour)
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              readOnly
              value={shareLink}
              style={shareLinkInput}
              onClick={(e: React.MouseEvent<HTMLInputElement>) => (e.target as HTMLInputElement).select()}
            />
            <button onClick={handleCopy} style={btnPrimary}>
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      {error && <div style={errorBox}>{error}</div>}

      {/* Paywall Modal - only show if not in sidecar mode (host app handles its own paywall) */}
      {showPaywall && !isSidecar && (
        <div style={modalOverlay}>
          <div style={modalContent}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🚀</div>
            <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 12 }}>Daily Limit Reached</h2>
            <p style={{ color: '#4b5563', marginBottom: 24, lineHeight: 1.5 }}>
              You've used your 5 free daily conversions. <br />
              Upgrade to <strong>Premium</strong> for unlimited processing, 
              larger files (up to 20MB), and advanced batch exports.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <button onClick={handleCheckout} style={{ ...btnPrimary, padding: '12px 24px', fontSize: 16 }}>
                Upgrade to Premium ($14.99)
              </button>
              <button onClick={() => setShowPaywall(false)} style={{ ...btnOutline, border: 'none', color: '#6b7280' }}>
                Maybe later
              </button>
            </div>
            <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 20 }}>
              Free tokens reset daily at 00:00 UTC.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = { maxWidth: 720, margin: '32px auto', fontFamily: 'sans-serif', padding: '0 16px' }
const headingStyle: CSSProperties = { fontSize: 22, fontWeight: 700, marginBottom: 6 }
const subtitleStyle: CSSProperties = { color: '#666', fontSize: 14, marginBottom: 20 }

const dropZoneStyle: CSSProperties = {
  border: '2px dashed #d1d5db', borderRadius: 12, padding: '36px 24px',
  textAlign: 'center', cursor: 'pointer', background: '#f9fafb',
}
const dropZoneActiveStyle: CSSProperties = { borderColor: '#2563eb', background: '#eff6ff' }
const dropIconStyle: CSSProperties = { fontSize: 28, marginBottom: 6, color: '#9ca3af' }

const fileListStyle: CSSProperties = { marginTop: 12, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }
const fileRowStyle: CSSProperties = { display: 'flex', alignItems: 'center', padding: '10px 14px', borderBottom: '1px solid #f3f4f6', background: '#fff' }
const fileIconStyle: CSSProperties = { marginRight: 10, fontSize: 16 }
const removeBtnStyle: CSSProperties = { background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 14, padding: '2px 4px' }

const jobContainerStyle: CSSProperties = { marginTop: 20, padding: 16, border: '1px solid #e5e7eb', borderRadius: 12, background: '#fff' }
const progressBgStyle: CSSProperties = { height: 8, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden' }
const progressFillStyle: CSSProperties = { height: '100%', transition: 'width 0.3s ease', borderRadius: 4 }

const actionsStyle: CSSProperties = { display: 'flex', gap: 10, marginTop: 14 }
const btnPrimary: CSSProperties = { padding: '9px 22px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 14, fontWeight: 600 }
const btnDisabled: CSSProperties = { ...btnPrimary, background: '#e5e7eb', color: '#9ca3af', cursor: 'not-allowed' }
const btnOutline: CSSProperties = { ...btnPrimary, background: '#fff', color: '#374151', border: '1px solid #d1d5db' }

const errorBox: CSSProperties = { background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 8, padding: '12px 16px', color: '#991b1b', marginTop: 14, fontSize: 14 }

const shareLinkBox: CSSProperties = { marginTop: 16, padding: 14, background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10 }
const shareLinkInput: CSSProperties = { flex: 1, fontSize: 12, padding: '7px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontFamily: 'monospace', background: '#fff', color: '#374151', minWidth: 0 }

const modalOverlay: CSSProperties = {
  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
  background: 'rgba(0, 0, 0, 0.4)', backdropFilter: 'blur(4px)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
}
const modalContent: CSSProperties = {
  background: '#fff', padding: 40, borderRadius: 24, maxWidth: 440, width: '90%',
  textAlign: 'center', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
}
