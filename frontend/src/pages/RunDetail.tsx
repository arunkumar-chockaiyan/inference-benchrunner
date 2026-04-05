import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, RunRead, WsEvent } from '../api'
import { StatusBadge } from '../components/StatusBadge'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RequestRecord {
  id: string
  prompt_id: string
  attempt: number
  status: string
  ttft_ms: number | null
  total_latency_ms: number
  tokens_per_second: number | null
  error_message: string | null
  started_at: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

function fmt(ms: number | null, decimals = 1): string {
  if (ms == null) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(decimals)}s` : `${ms.toFixed(decimals)}ms`
}

function fmtSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${m}m ${sec}s`
}

function ConfigRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between py-1.5 border-b border-gray-100 last:border-0 text-sm">
      <span className="text-gray-500 w-40 shrink-0">{label}</span>
      <span className="text-gray-900 text-right">{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunDetail
// ---------------------------------------------------------------------------

export default function RunDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [run, setRun] = useState<RunRead | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [wsData, setWsData] = useState<WsEvent | null>(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [records, setRecords] = useState<RequestRecord[]>([])
  const [recordsLoading, setRecordsLoading] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // Load run
  const loadRun = () => {
    if (!id) return
    api
      .getRun(id)
      .then((r) => {
        setRun(r)
        setLoading(false)
        // Load request records
        setRecordsLoading(true)
        fetch(`/api/runs/${id}/requests?limit=20`)
          .then((res) => res.json())
          .then((data) => setRecords(data.items ?? []))
          .catch(() => {})
          .finally(() => setRecordsLoading(false))
      })
      .catch((e: Error) => {
        setError(e.message)
        setLoading(false)
      })
  }

  useEffect(() => {
    loadRun()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // WebSocket
  useEffect(() => {
    if (!id) return

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${proto}//${location.host}/ws/runs/${id}`)
      wsRef.current = ws

      ws.onmessage = (e) => {
        const evt: WsEvent = JSON.parse(e.data)
        setWsData(evt)
        if (TERMINAL.has(evt.status)) {
          // Refresh run record on terminal state
          loadRun()
          ws.close(1000)
        }
      }

      ws.onclose = (e) => {
        if (e.code !== 1000) {
          // Unexpected close — reconnect after 3s
          setTimeout(connect, 3000)
        }
      }
    }

    connect()
    return () => {
      wsRef.current?.close(1000)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const handleCancel = async () => {
    if (!id || !window.confirm('Cancel this run?')) return
    try {
      await api.cancelRun(id)
      loadRun()
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  // ---------------------------------------------------------------------------
  // Loading / error
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  if (error || !run) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4">
          <p className="text-red-700 text-sm">{error ?? 'Run not found'}</p>
          <button
            onClick={() => navigate('/')}
            className="mt-2 text-sm text-red-700 underline hover:text-red-900"
          >
            ← Back to runs
          </button>
        </div>
      </div>
    )
  }

  const status = wsData?.status ?? run.status
  const completed = wsData?.completed ?? run.completed_requests
  const total = wsData?.total ?? run.total_requests
  const failed = wsData?.failed ?? run.failed_requests
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0
  const grafanaUrl = `http://localhost:3001/d/bench-dashboard/bench?var-run_id=${run.id}`

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate('/')}
            className="text-sm text-gray-500 hover:text-gray-700 mb-1 block"
          >
            ← Runs
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-gray-900">
              {run.config.name}
            </h1>
            <StatusBadge status={status} />
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            {run.config.engine} · {run.config.model} · {run.config.host}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status === 'running' && (
            <button
              onClick={handleCancel}
              className="bg-white text-red-600 border border-red-300 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-red-50 transition-colors"
            >
              Cancel
            </button>
          )}
          <a
            href={grafanaUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="bg-white text-gray-700 border border-gray-300 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors flex items-center gap-1"
          >
            <span>📊</span> Grafana
          </a>
        </div>
      </div>

      {/* Error banner */}
      {run.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-3">
          <p className="text-sm font-medium text-red-800">Run failed</p>
          <p className="text-sm text-red-700 mt-0.5">{run.error_message}</p>
        </div>
      )}

      {/* Cleanup warning */}
      {run.cleanup_warning && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl px-5 py-3">
          <p className="text-sm text-yellow-800">⚠ {run.cleanup_warning}</p>
        </div>
      )}

      {/* Live progress (active runs) */}
      {!TERMINAL.has(status) && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-gray-700">Progress</span>
            <span className="text-sm text-gray-500">{completed} / {total} requests</span>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-gray-200 rounded-full h-2 mb-4">
            <div
              className="bg-indigo-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>

          {/* Live stats */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <StatCard label="Progress" value={`${pct}%`} />
            <StatCard label="Tok/s" value={wsData?.current_tps != null ? wsData.current_tps.toFixed(1) : '—'} />
            <StatCard label="Elapsed" value={wsData ? fmtSeconds(wsData.elapsed_seconds) : '—'} />
            <StatCard label="ETA" value={wsData?.eta_seconds != null ? fmtSeconds(wsData.eta_seconds) : '—'} />
            <StatCard
              label="Server"
              value={
                wsData ? (
                  <span className={`flex items-center gap-1 ${wsData.server_alive ? 'text-green-600' : 'text-red-600'}`}>
                    <span className={`w-2 h-2 rounded-full ${wsData.server_alive ? 'bg-green-500' : 'bg-red-500'}`} />
                    {wsData.server_alive ? 'alive' : 'offline'}
                  </span>
                ) : '—'
              }
            />
          </div>

          {failed > 0 && (
            <p className="mt-3 text-xs text-red-600">{failed} request{failed !== 1 ? 's' : ''} failed</p>
          )}
        </div>
      )}

      {/* Completed stats */}
      {TERMINAL.has(status) && total > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Results</h3>
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Total" value={String(total)} />
            <StatCard label="Completed" value={String(run.completed_requests)} />
            <StatCard label="Failed" value={String(run.failed_requests)} />
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-medium text-gray-700 mb-3">Timeline</h3>
        <div className="flex items-start gap-1 flex-wrap text-xs text-gray-600">
          <TimelineItem
            label="Created"
            ts={null}
            note={null}
          />
          <TimelineArrow />
          <TimelineItem
            label="Started"
            ts={run.started_at}
            note={null}
          />
          <TimelineArrow />
          <TimelineItem
            label="Warmup done"
            ts={run.run_started_at}
            note={run.warmup_duration_ms != null ? `${(run.warmup_duration_ms / 1000).toFixed(1)}s warmup` : null}
          />
          <TimelineArrow />
          <TimelineItem
            label={status === 'failed' ? 'Failed' : status === 'cancelled' ? 'Cancelled' : 'Completed'}
            ts={run.completed_at}
            note={null}
          />
        </div>
      </div>

      {/* Config (collapsible) */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <button
          onClick={() => setConfigOpen((o) => !o)}
          className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <span>Run configuration</span>
          <span className="text-gray-400">{configOpen ? '▲' : '▼'}</span>
        </button>
        {configOpen && (
          <div className="px-5 pb-4 border-t border-gray-100">
            <ConfigRow label="Engine" value={run.config.engine} />
            <ConfigRow label="Model" value={run.config.model} />
            <ConfigRow label="Host" value={`${run.config.host}:${run.config.port}`} />
            <ConfigRow label="Spawn mode" value={run.config.spawn_mode} />
            <ConfigRow label="Concurrency" value={run.config.concurrency} />
            <ConfigRow label="Temperature" value={run.config.temperature} />
            <ConfigRow label="Max tokens" value={run.config.max_tokens} />
            {run.config.tags.length > 0 && (
              <ConfigRow label="Tags" value={run.config.tags.join(', ')} />
            )}
            {run.config.notes && <ConfigRow label="Notes" value={run.config.notes} />}
          </div>
        )}
      </div>

      {/* Request log */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <h3 className="text-sm font-medium text-gray-700">Request log</h3>
        </div>
        {recordsLoading ? (
          <div className="p-5 text-center text-sm text-gray-500">Loading…</div>
        ) : records.length === 0 ? (
          <div className="p-5 text-center text-sm text-gray-500">No requests recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-4 py-2 text-left text-gray-500 font-medium">#</th>
                  <th className="px-4 py-2 text-left text-gray-500 font-medium">Status</th>
                  <th className="px-4 py-2 text-right text-gray-500 font-medium">TTFT</th>
                  <th className="px-4 py-2 text-right text-gray-500 font-medium">Latency</th>
                  <th className="px-4 py-2 text-right text-gray-500 font-medium">Tok/s</th>
                  <th className="px-4 py-2 text-left text-gray-500 font-medium">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {records.map((rec, i) => (
                  <tr key={rec.id} className={rec.status === 'error' ? 'bg-red-50' : ''}>
                    <td className="px-4 py-2 text-gray-400">{i + 1}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`font-medium ${rec.status === 'success' ? 'text-green-700' : 'text-red-700'}`}
                      >
                        {rec.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right text-gray-700">{fmt(rec.ttft_ms)}</td>
                    <td className="px-4 py-2 text-right text-gray-700">{fmt(rec.total_latency_ms)}</td>
                    <td className="px-4 py-2 text-right text-gray-700">
                      {rec.tokens_per_second != null ? rec.tokens_per_second.toFixed(1) : '—'}
                    </td>
                    <td className="px-4 py-2 text-gray-400">
                      {new Date(rec.started_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2.5">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="text-sm font-semibold text-gray-900">{value}</div>
    </div>
  )
}

function TimelineItem({ label, ts, note }: { label: string; ts: string | null; note: string | null }) {
  return (
    <div className="flex flex-col items-center min-w-[80px]">
      <div className="w-2.5 h-2.5 rounded-full bg-indigo-400 mb-1" />
      <span className="font-medium text-gray-700">{label}</span>
      {ts && (
        <span className="text-gray-400 text-[10px] mt-0.5">
          {new Date(ts).toLocaleTimeString()}
        </span>
      )}
      {note && <span className="text-indigo-600 text-[10px]">{note}</span>}
    </div>
  )
}

function TimelineArrow() {
  return <div className="flex-1 border-t-2 border-dashed border-gray-200 mt-1.5 min-w-[16px]" />
}
