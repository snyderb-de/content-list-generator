import { useEffect, useState } from 'react'
import { GetAppVersion } from '../../wailsjs/go/main/App'
import { BrowserOpenURL } from '../../wailsjs/runtime/runtime'

export default function About() {
  const [version, setVersion] = useState('…')

  useEffect(() => {
    GetAppVersion().then(setVersion).catch(() => setVersion('unknown'))
  }, [])

  return (
    <div>
      <div className="screen-header">
        <h2 className="screen-title">About</h2>
        <p className="screen-subtitle">Content List Generator v{version}</p>
      </div>

      <div className="card">
        <p className="card-title">What it does</p>
        <p className="info-text" style={{ marginBottom: 12 }}>
          Fast recursive folder scanner for very large collections. Generate a full CSV inventory
          with optional XLSX export, copy email files to a destination while preserving folder
          structure, or compare two drives to verify a clone.
        </p>
        <p className="info-text">
          CSV output streams directly to disk — no in-memory table — so scans of millions of files
          are handled without running out of memory. Files are split automatically at 300&thinsp;000
          rows per part.
        </p>

        <div className="divider" />

        <div className="stat-row">
          <span className="stat-row-label">Version</span>
          <span className="stat-row-value">{version}</span>
        </div>
        <div className="stat-row">
          <span className="stat-row-label">Runtime</span>
          <span className="stat-row-value">Go + Wails v2 + React</span>
        </div>
        <div className="stat-row">
          <span className="stat-row-label">Hash algorithms</span>
          <span className="stat-row-value">BLAKE3, SHA-1, SHA-256</span>
        </div>
        <div className="stat-row">
          <span className="stat-row-label">CSV row limit</span>
          <span className="stat-row-value">300,000 rows / part (auto-split)</span>
        </div>
        <div className="stat-row">
          <span className="stat-row-label">GitHub</span>
          <span className="stat-row-value">
            <button
              className="btn btn-ghost"
              style={{ padding: 0, color: 'var(--accent)', fontWeight: 500, fontSize: 13 }}
              onClick={() => BrowserOpenURL('https://github.com/snyderb-de/content-list-generator')}
            >
              github.com/snyderb-de/content-list-generator
            </button>
          </span>
        </div>
      </div>
    </div>
  )
}
