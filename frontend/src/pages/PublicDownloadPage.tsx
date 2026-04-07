/**
 * Public download page — accessible without authentication.
 *
 * In sidecar mode: the main YFW platform iframes this page at
 * /plugins/statement-tools/public/?token={token} when a user visits
 * /p/statement-tools?token={token}.
 *
 * In standalone mode: accessible directly at
 * /statement-tools/public?token={token}.
 *
 * Reads the token from the URL search params and triggers a direct
 * download from the backend's public download endpoint.
 */
import React, { useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { recordPublicUsage } from '@/lib/publicUsage'
import { statementsApi } from '@/api/statements'

export default function PublicDownloadPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')
  const [downloaded, setDownloaded] = useState(false)

  if (!token) {
    return (
      <div style={pageStyle}>
        <div style={cardStyle}>
          <div style={iconStyle}>📋</div>
          <h1 style={headingStyle}>Invalid Link</h1>
          <p style={subtitleStyle}>
            This link is missing a download token. Please request a new download link.
          </p>
        </div>
      </div>
    )
  }

  async function handleDownload() {
    if (!token) return
    setDownloading(true)
    setError('')

    try {
      // Trigger the download by navigating to the backend endpoint.
      // The browser handles the file download directly — no auth header needed.
      const url = statementsApi.downloadUrl(token)
      const link = document.createElement('a')
      link.href = url
      link.click()
      setDownloaded(true)
      recordPublicUsage('statements/download')
    } catch (e: unknown) {
      const msg = (e as Error).message
      if (msg.includes('410') || msg.toLowerCase().includes('expired')) {
        setError('This download link has expired. Please request a new one.')
      } else {
        setError(msg || 'Download failed. Please try again.')
      }
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div style={iconStyle}>📊</div>
        <h1 style={headingStyle}>Download Statement CSV</h1>
        <p style={subtitleStyle}>
          Your merged bank statement CSV is ready to download.
          This link expires after 1 hour.
        </p>

        {downloaded && !error && (
          <div style={successBox}>
            Download started. Check your browser's downloads folder.
          </div>
        )}

        {error && <div style={errorBox}>{error}</div>}

        {!error && (
          <button
            onClick={handleDownload}
            disabled={downloading}
            style={downloading ? btnDisabled : btnPrimary}
          >
            {downloading ? 'Preparing download...' : '⬇ Download CSV'}
          </button>
        )}

        <p style={noteStyle}>
          Processed by YourFinanceWORKS · No login required
        </p>
      </div>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: '#f9fafb',
  fontFamily: 'sans-serif',
  padding: '16px',
}
const cardStyle: CSSProperties = {
  background: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: '40px 32px',
  maxWidth: 420,
  width: '100%',
  textAlign: 'center',
  boxShadow: '0 1px 3px rgba(0,0,0,0.07)',
}
const iconStyle: CSSProperties = { fontSize: 40, marginBottom: 12 }
const headingStyle: CSSProperties = { fontSize: 20, fontWeight: 700, margin: '0 0 8px' }
const subtitleStyle: CSSProperties = { color: '#6b7280', fontSize: 14, marginBottom: 24 }
const noteStyle: CSSProperties = { color: '#9ca3af', fontSize: 12, marginTop: 20 }

const btnPrimary: CSSProperties = {
  padding: '10px 28px',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: 15,
  fontWeight: 600,
}
const btnDisabled: CSSProperties = { ...btnPrimary, background: '#e5e7eb', color: '#9ca3af', cursor: 'not-allowed' }

const successBox: CSSProperties = {
  background: '#f0fdf4',
  border: '1px solid #86efac',
  borderRadius: 8,
  padding: '12px 16px',
  color: '#166534',
  fontSize: 14,
  marginBottom: 16,
}
const errorBox: CSSProperties = {
  background: '#fef2f2',
  border: '1px solid #fca5a5',
  borderRadius: 8,
  padding: '12px 16px',
  color: '#991b1b',
  fontSize: 14,
  marginBottom: 16,
}
