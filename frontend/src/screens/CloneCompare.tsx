import { useEffect, useRef, useState } from 'react'
import { CancelCloneCompare, OpenPath, StartCloneCompare } from '../../wailsjs/go/main/App'
import { EventsOff, EventsOn } from '../../wailsjs/runtime/runtime'
import FolderPicker from '../components/FolderPicker'
import ProgressBar from '../components/ProgressBar'
import {
  CloneCompareOptions, CloneDonePayload,
  CloneProgressPayload, DiffRowPayload,
  HASH_ALGORITHMS,
} from '../types'

type Phase = 'idle' | 'running' | 'done' | 'error' | 'canceled'

const DIFF_ROW_CAP = 5000

function fmtNum(n: number) { return n.toLocaleString() }
function fmtSecs(s: number) {
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  return `${m}m ${(s % 60).toFixed(0)}s`
}

function diffTypeBadge(type: string) {
  if (type.includes('missing')) return 'diff-type-missing'
  if (type.includes('extra'))   return 'diff-type-extra'
  return 'diff-type-mismatch'
}

function phaseLabel(phase: string) {
  if (phase === 'scan-a') return 'Scanning 1st Drive'
  if (phase === 'scan-b') return 'Scanning 2nd Drive'
  if (phase === 'diff')   return 'Comparing Drives'
  return 'Starting…'
}

function phaseStep(phase: string) {
  if (phase === 'scan-a') return 1
  if (phase === 'scan-b') return 2
  if (phase === 'diff')   return 3
  return 0
}

export default function CloneCompare() {
  const [opts, setOpts] = useState<CloneCompareOptions>({
    driveA: '', driveB: '', outputDir: '', hashAlgorithm: 'blake3',
  })
  const [phase, setPhase]       = useState<Phase>('idle')
  const [clonePhase, setClonePhase] = useState('')
  const [progress, setProgress] = useState<CloneProgressPayload | null>(null)
  const [diffRows, setDiffRows] = useState<DiffRowPayload[]>([])
  const [hiddenRows, setHiddenRows] = useState(0)
  const [result, setResult]     = useState<CloneDonePayload | null>(null)
  const [err, setErr]           = useState('')
  const tableEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    return () => {
      EventsOff('clone:progress')
      EventsOff('clone:diff-row')
      EventsOff('clone:done')
      EventsOff('clone:error')
      EventsOff('clone:canceled')
    }
  }, [])

  useEffect(() => {
    if (diffRows.length > 0) {
      tableEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [diffRows.length])

  const set = (key: keyof CloneCompareOptions, value: string) =>
    setOpts(o => ({ ...o, [key]: value }))

  const start = async () => {
    if (opts.driveA.trim() === opts.driveB.trim()) {
      setErr('1st Drive and 2nd Drive must be different folders.')
      setPhase('error')
      return
    }
    setPhase('running')
    setClonePhase('')
    setProgress(null)
    setDiffRows([])
    setHiddenRows(0)
    setErr('')

    EventsOn('clone:progress', (d: CloneProgressPayload) => {
      setClonePhase(d.phase)
      setProgress(d)
    })
    EventsOn('clone:diff-row', (d: DiffRowPayload) => {
      setDiffRows(prev => {
        if (prev.length >= DIFF_ROW_CAP) {
          setHiddenRows(h => h + 1)
          return prev
        }
        return [...prev, d]
      })
    })
    EventsOn('clone:done',     (d: CloneDonePayload) => { setResult(d); setPhase('done') })
    EventsOn('clone:error',    (msg: string)         => { setErr(msg); setPhase('error') })
    EventsOn('clone:canceled', ()                    => setPhase('canceled'))

    try {
      await StartCloneCompare(opts)
    } catch (e: any) {
      EventsOff('clone:progress'); EventsOff('clone:diff-row')
      EventsOff('clone:done');     EventsOff('clone:error'); EventsOff('clone:canceled')
      setErr(String(e))
      setPhase('error')
    }
  }

  const cancel = () => CancelCloneCompare().catch(() => {})

  const reset = () => {
    EventsOff('clone:progress'); EventsOff('clone:diff-row')
    EventsOff('clone:done');     EventsOff('clone:error'); EventsOff('clone:canceled')
    setPhase('idle'); setProgress(null); setDiffRows([]); setHiddenRows(0); setResult(null); setErr('')
  }

  const drivesMismatch = !!(opts.driveA && opts.driveB && opts.driveA === opts.driveB)
  const canStart = opts.driveA && opts.driveB && opts.outputDir && !drivesMismatch

  // ── Form ──────────────────────────────────────────────────
  if (phase === 'idle' || phase === 'canceled') {
    return (
      <div>
        <div className="screen-header">
          <h2 className="screen-title">Clone Compare</h2>
          <p className="screen-subtitle">Scan two drives and diff the results to verify a clone.</p>
        </div>

        {phase === 'canceled' && (
          <div className="card" style={{ marginBottom: 16 }}>
            <span className="danger-text">Comparison was stopped.</span>
          </div>
        )}

        <div className="card">
          <p className="card-title">Drives</p>
          <FolderPicker label="1st Drive (Source)" value={opts.driveA}    onChange={v => set('driveA', v)} />
          <FolderPicker label="2nd Drive (Clone)"  value={opts.driveB}    onChange={v => set('driveB', v)} />
          {drivesMismatch && (
            <p className="danger-text" style={{ margin: '4px 0 8px' }}>
              1st Drive and 2nd Drive must be different folders.
            </p>
          )}
          <FolderPicker label="Output Folder"     value={opts.outputDir} onChange={v => set('outputDir', v)} />
          <div className="field">
            <label className="field-label">Hash Algorithm</label>
            <select className="select" value={opts.hashAlgorithm} onChange={e => set('hashAlgorithm', e.target.value)}>
              {HASH_ALGORITHMS.filter(h => h.value !== 'off').map(h => (
                <option key={h.value} value={h.value}>{h.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="info-text" style={{ margin: '12px 0' }}>
          Scans both drives sequentially using the same hash algorithm, then diffs the CSV outputs.
          Files are compared by relative path, size, and hash value.
        </div>

        <button className="btn btn-primary btn-lg" onClick={start} disabled={!canStart}>
          Start Compare
        </button>
      </div>
    )
  }

  // ── Running ───────────────────────────────────────────────
  if (phase === 'running') {
    const step = phaseStep(clonePhase)
    const pct  = progress?.percent ?? 0

    return (
      <div>
        <div className="screen-header">
          <h2 className="screen-title">Comparing…</h2>
          <p className="screen-subtitle">{phaseLabel(clonePhase)}</p>
        </div>

        <div className="card">
          {/* 3-phase indicator */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {(['scan-a', 'scan-b', 'diff'] as const).map((s, i) => (
              <div key={s} style={{
                flex: 1,
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                fontSize: 12,
                fontWeight: 600,
                textAlign: 'center',
                background: step > i ? 'var(--success-bg)' : step === i ? 'var(--accent-light)' : 'var(--bg-input)',
                color: step > i ? 'var(--success)' : step === i ? 'var(--accent)' : 'var(--text-muted)',
                border: `1px solid ${step === i ? 'var(--accent)' : 'var(--border)'}`,
              }}>
                {i + 1}. {phaseLabel(s)}
              </div>
            ))}
          </div>

          <ProgressBar percent={pct} animated={clonePhase !== 'diff' || pct === 0} />

          <div className="stat-grid" style={{ marginBottom: 12 }}>
            <div className="stat-block">
              <div className="stat-block-label">Progress</div>
              <div className="stat-block-value">{`${(pct * 100).toFixed(1)}%`}</div>
            </div>
            <div className="stat-block">
              <div className="stat-block-label">Compared</div>
              <div className="stat-block-value">{fmtNum(progress?.compared ?? 0)}</div>
            </div>
            <div className="stat-block">
              <div className="stat-block-label">Differences</div>
              <div className="stat-block-value" style={{ color: (progress?.differences ?? 0) > 0 ? 'var(--danger)' : 'inherit' }}>
                {fmtNum(progress?.differences ?? 0)}
              </div>
            </div>
          </div>

          {progress?.currentItem && (
            <div className="current-file">{progress.currentItem}</div>
          )}

          <button className="btn btn-danger" style={{ marginTop: 12 }} onClick={cancel}>
            Stop
          </button>
        </div>

        {/* Live diff table */}
        {diffRows.length > 0 && (
          <div className="card">
            <p className="card-title">Live Differences ({fmtNum(diffRows.length)}{hiddenRows > 0 ? ` + ${fmtNum(hiddenRows)} more` : ''})</p>
            <div className="diff-table-wrap">
              <table className="diff-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Path</th>
                    <th>Size A</th>
                    <th>Size B</th>
                  </tr>
                </thead>
                <tbody>
                  {diffRows.map((row, i) => (
                    <tr key={i}>
                      <td><span className={`diff-type-badge ${diffTypeBadge(row.diffType)}`}>{row.diffType}</span></td>
                      <td title={row.path}>{row.path}</td>
                      <td>{row.sizeA}</td>
                      <td>{row.sizeB}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div ref={tableEndRef} />
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── Error ─────────────────────────────────────────────────
  if (phase === 'error') {
    return (
      <div>
        <div className="screen-header"><h2 className="screen-title">Compare Failed</h2></div>
        <div className="card">
          <p className="danger-text" style={{ marginBottom: 16 }}>Error: {err}</p>
          <button className="btn btn-outline" onClick={reset}>Back to Settings</button>
        </div>
      </div>
    )
  }

  // ── Done ──────────────────────────────────────────────────
  if (!result) return null

  const hasDiffs = result.differences > 0

  return (
    <div>
      <div className="screen-header">
        <h2 className="screen-title">Compare Complete</h2>
        <p className={`screen-subtitle ${hasDiffs ? 'danger-text' : 'success-text'}`}>
          {hasDiffs ? `${fmtNum(result.differences)} differences found` : 'Drives match — no differences'}
        </p>
      </div>

      <div className="card">
        <p className="card-title">Results</p>
        <div className="stat-grid" style={{ marginBottom: 16 }}>
          <div className="stat-block">
            <div className="stat-block-label">Paths Checked</div>
            <div className="stat-block-value">{fmtNum(result.compared)}</div>
          </div>
          <div className="stat-block">
            <div className="stat-block-label">Total Differences</div>
            <div className="stat-block-value" style={{ color: hasDiffs ? 'var(--danger)' : 'var(--success)' }}>
              {fmtNum(result.differences)}
            </div>
          </div>
          <div className="stat-block">
            <div className="stat-block-label">Missing from Clone</div>
            <div className="stat-block-value">{fmtNum(result.missingFromDriveB)}</div>
          </div>
          <div className="stat-block">
            <div className="stat-block-label">Extra on Clone</div>
            <div className="stat-block-value">{fmtNum(result.extraOnDriveB)}</div>
          </div>
          <div className="stat-block">
            <div className="stat-block-label">Size Mismatches</div>
            <div className="stat-block-value">{fmtNum(result.sizeMismatches)}</div>
          </div>
          <div className="stat-block">
            <div className="stat-block-label">Hash Mismatches</div>
            <div className="stat-block-value">{fmtNum(result.hashMismatches)}</div>
          </div>
          <div className="stat-block">
            <div className="stat-block-label">Hash Algorithm</div>
            <div className="stat-block-value">{result.hashAlgorithm.toUpperCase()}</div>
          </div>
          <div className="stat-block">
            <div className="stat-block-label">Elapsed</div>
            <div className="stat-block-value">{fmtSecs(result.elapsedSecs)}</div>
          </div>
        </div>

        {result.diffPath && <div className="stat-row"><span className="stat-row-label">Diff CSV</span><span className="stat-row-value">{result.diffPath}</span></div>}
        {result.reportPath && <div className="stat-row"><span className="stat-row-label">Report</span><span className="stat-row-value">{result.reportPath}</span></div>}

        <div className="result-actions">
          {result.diffPath && <button className="btn btn-primary" onClick={() => OpenPath(result.diffPath)}>Open Diff CSV</button>}
          {result.reportPath && <button className="btn btn-outline" onClick={() => OpenPath(result.reportPath)}>Open Report</button>}
          <button className="btn btn-ghost" onClick={reset}>New Compare</button>
        </div>
      </div>

      {/* Full diff table */}
      {diffRows.length > 0 && (
        <div className="card">
          <p className="card-title">
            Differences ({fmtNum(diffRows.length)}
            {hiddenRows > 0 && ` shown · ${fmtNum(hiddenRows)} more in CSV`})
          </p>
          <div className="diff-table-wrap">
            <table className="diff-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Path</th>
                  <th>Size A</th>
                  <th>Size B</th>
                  <th>Hash A</th>
                  <th>Hash B</th>
                </tr>
              </thead>
              <tbody>
                {diffRows.map((row, i) => (
                  <tr key={i}>
                    <td><span className={`diff-type-badge ${diffTypeBadge(row.diffType)}`}>{row.diffType}</span></td>
                    <td title={row.path}>{row.path}</td>
                    <td>{row.sizeA}</td>
                    <td>{row.sizeB}</td>
                    <td title={row.hashA}>{row.hashA ? row.hashA.slice(0, 12) + '…' : ''}</td>
                    <td title={row.hashB}>{row.hashB ? row.hashB.slice(0, 12) + '…' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
