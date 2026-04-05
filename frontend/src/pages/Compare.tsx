import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ErrorBar,
  Legend,
} from 'recharts'
import { api, RunStats, RunSummary } from '../api'
import { StatusBadge } from '../components/StatusBadge'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

type Metric = 'p99' | 'ttft' | 'throughput'

const METRIC_OPTS: { key: Metric; label: string }[] = [
  { key: 'p99', label: 'p99 Latency' },
  { key: 'ttft', label: 'TTFT' },
  { key: 'throughput', label: 'Throughput (tok/s)' },
]

function getMetricValue(stats: RunStats, metric: Metric): number | null {
  if (metric === 'p99') return stats.p99_latency_ms
  if (metric === 'ttft') return stats.p99_ttft_ms
  return stats.avg_tokens_per_sec
}

function getStddev(stats: RunStats, metric: Metric): number | null {
  if (metric === 'p99') return stats.stddev_latency_ms
  return null  // stddev not available for ttft or throughput
}

function metricUnit(metric: Metric): string {
  if (metric === 'throughput') return ' tok/s'
  return ' ms'
}

function runLabel(stats: RunStats): string {
  const model = stats.model.split('/').pop() ?? stats.model
  return `${stats.engine}/${model.length > 16 ? model.slice(0, 16) + '…' : model}`
}

function fmtNum(n: number | null, decimals = 1): string {
  if (n == null) return '—'
  return n.toFixed(decimals)
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

export default function Compare() {
  const [searchParams] = useSearchParams()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>(() => {
    const ids = searchParams.get('ids')
    return ids ? ids.split(',').filter(Boolean) : []
  })
  const [metric, setMetric] = useState<Metric>('p99')
  const [stats, setStats] = useState<RunStats[]>([])
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState<string | null>(null)

  // Load runs list for selection
  useEffect(() => {
    setRunsLoading(true)
    api
      .listRuns({ limit: 50 })
      .then(({ items }) => setRuns(items))
      .catch(() => {})
      .finally(() => setRunsLoading(false))
  }, [])

  const toggleId = (id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 6) return prev
      return [...prev, id]
    })
  }

  const handleCompare = () => {
    if (selectedIds.length < 2) return
    setStatsLoading(true)
    setStatsError(null)
    api
      .compareRuns(selectedIds, metric)
      .then(({ runs: r }) => setStats(r))
      .catch((e: Error) => setStatsError(e.message))
      .finally(() => setStatsLoading(false))
  }

  // Auto-compare when ids come from URL and are 2+
  useEffect(() => {
    if (selectedIds.length >= 2) handleCompare()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSave = async () => {
    if (stats.length === 0) return
    const name = window.prompt(
      'Name this comparison:',
      `${metric} — ${new Date().toLocaleDateString()}`,
    )
    if (!name) return
    try {
      const result = await fetch('/api/comparisons', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, run_ids: selectedIds, metric }),
      }).then((r) => r.json())
      const url = `${window.location.origin}/compare?token=${result.share_token}`
      alert(`Saved! Shareable URL:\n${url}`)
    } catch {
      alert('Failed to save comparison.')
    }
  }

  // Build chart data
  const chartData = stats.map((s) => ({
    name: runLabel(s),
    value: getMetricValue(s, metric) ?? 0,
    errorY: getStddev(s, metric) != null ? [getStddev(s, metric)!, getStddev(s, metric)!] : undefined,
  }))

  // Best-value detection per summary row
  const getRowBest = (field: keyof RunStats, lowerIsBetter = true): string | null => {
    const vals = stats
      .map((s) => ({ id: s.run_id, v: s[field] as number | null }))
      .filter((x) => x.v != null)
    if (vals.length === 0) return null
    const best = lowerIsBetter
      ? vals.reduce((a, b) => (a.v! < b.v! ? a : b))
      : vals.reduce((a, b) => (a.v! > b.v! ? a : b))
    return best.id
  }

  const summaryRows: Array<{ label: string; field: keyof RunStats; lower?: boolean }> = [
    { label: 'Avg latency', field: 'avg_latency_ms', lower: true },
    { label: 'p50 latency', field: 'p50_latency_ms', lower: true },
    { label: 'p99 latency', field: 'p99_latency_ms', lower: true },
    { label: 'Min latency', field: 'min_latency_ms', lower: true },
    { label: 'Max latency', field: 'max_latency_ms', lower: true },
    { label: 'Std dev', field: 'stddev_latency_ms', lower: true },
    { label: 'Avg TTFT', field: 'avg_ttft_ms', lower: true },
    { label: 'p99 TTFT', field: 'p99_ttft_ms', lower: true },
    { label: 'Avg tok/s', field: 'avg_tokens_per_sec', lower: false },
    { label: 'Total reqs', field: 'total_requests', lower: false },
    { label: 'Failed', field: 'failed_requests', lower: true },
    { label: 'Samples', field: 'sample_count', lower: false },
  ]

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Compare runs</h1>
        {stats.length >= 2 && (
          <button
            onClick={handleSave}
            className="bg-white text-gray-700 px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50 text-sm font-medium transition-colors"
          >
            Save comparison
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Run selection panel */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-medium text-gray-700">
              Select runs{' '}
              <span className="text-gray-400 font-normal">
                ({selectedIds.length}/6)
              </span>
            </h2>
          </div>
          {runsLoading ? (
            <div className="p-4 space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : runs.length === 0 ? (
            <div className="p-4 text-sm text-gray-500 text-center">No runs available.</div>
          ) : (
            <ul className="divide-y divide-gray-50 max-h-96 overflow-y-auto">
              {runs.map((run) => {
                const selected = selectedIds.includes(run.id)
                const disabled = !selected && selectedIds.length >= 6
                return (
                  <li key={run.id}>
                    <label
                      className={`flex items-start gap-3 px-4 py-2.5 cursor-pointer transition-colors text-sm ${
                        selected ? 'bg-indigo-50' : disabled ? 'opacity-40' : 'hover:bg-gray-50'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        disabled={disabled}
                        onChange={() => toggleId(run.id)}
                        className="mt-0.5 w-4 h-4 text-indigo-600 border-gray-300 rounded"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900 truncate">
                            {run.engine}/{run.model}
                          </span>
                          <StatusBadge status={run.status} />
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          #{run.id.slice(0, 8)}
                        </div>
                      </div>
                    </label>
                  </li>
                )
              })}
            </ul>
          )}
          <div className="px-4 py-3 border-t border-gray-100 flex gap-2">
            <button
              onClick={handleCompare}
              disabled={selectedIds.length < 2 || statsLoading}
              className="flex-1 bg-indigo-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {statsLoading ? 'Computing…' : 'Compare'}
            </button>
          </div>
        </div>

        {/* Chart + results */}
        <div className="lg:col-span-2 space-y-5">
          {/* Metric selector */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex gap-2">
              {METRIC_OPTS.map((opt) => (
                <button
                  key={opt.key}
                  onClick={() => setMetric(opt.key)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    metric === opt.key
                      ? 'bg-indigo-600 text-white'
                      : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {statsError && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
              {statsError}
            </div>
          )}

          {/* Bar chart */}
          {stats.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-medium text-gray-700 mb-4">
                {METRIC_OPTS.find((m) => m.key === metric)?.label}
                <span className="text-gray-400 font-normal ml-1">{metricUnit(metric)}</span>
              </h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11 }}
                    angle={-20}
                    textAnchor="end"
                    interval={0}
                    height={60}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number) => [`${value.toFixed(2)}${metricUnit(metric)}`, 'Value']}
                  />
                  <Legend />
                  <Bar dataKey="value" name={METRIC_OPTS.find((m) => m.key === metric)?.label ?? metric}>
                    {chartData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                    {chartData.some((d) => d.errorY) && (
                      <ErrorBar dataKey="errorY" width={4} strokeWidth={2} stroke="#999" />
                    )}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Scorecard table */}
          {stats.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100">
                <h3 className="text-sm font-medium text-gray-700">Summary</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="px-4 py-2.5 text-left text-gray-500 font-medium w-28">Metric</th>
                      {stats.map((s, i) => (
                        <th
                          key={s.run_id}
                          className="px-4 py-2.5 text-right text-gray-500 font-medium"
                          style={{ color: COLORS[i % COLORS.length] }}
                        >
                          {runLabel(s)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {summaryRows.map(({ label, field, lower = true }) => {
                      const bestId = getRowBest(field, lower)
                      return (
                        <tr key={field}>
                          <td className="px-4 py-2 font-medium text-gray-600">{label}</td>
                          {stats.map((s) => {
                            const val = s[field] as number | null
                            const isBest = bestId === s.run_id && val != null
                            return (
                              <td
                                key={s.run_id}
                                className={`px-4 py-2 text-right ${
                                  isBest ? 'bg-green-50 text-green-700 font-semibold' : 'text-gray-700'
                                }`}
                              >
                                {fmtNum(val)}
                              </td>
                            )
                          })}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {stats.length === 0 && !statsLoading && (
            <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-sm text-gray-500">
              Select 2 or more runs and click Compare to see results.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
