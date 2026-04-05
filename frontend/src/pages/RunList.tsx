import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import { useAppStore } from '../store'

const ENGINE_OPTIONS = ['All', 'ollama', 'llamacpp', 'vllm', 'sglang'] as const
const STATUS_OPTIONS = ['All', 'running', 'completed', 'failed', 'cancelled'] as const

function formatDuration(started: string | null, completed: string | null): string {
  if (!started || !completed) return '—'
  const diff = (new Date(completed).getTime() - new Date(started).getTime()) / 1000
  if (diff < 60) return `${diff.toFixed(1)}s`
  const m = Math.floor(diff / 60)
  const s = Math.round(diff % 60)
  return `${m}m ${s}s`
}

function SkeletonRow() {
  return (
    <tr className="border-b border-gray-100">
      {Array.from({ length: 8 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div
            className="h-4 bg-gray-200 rounded animate-pulse"
            style={{ width: i === 0 ? '20px' : i === 7 ? '40px' : '80%' }}
          />
        </td>
      ))}
    </tr>
  )
}

export default function RunList() {
  const navigate = useNavigate()
  const { runs, runsLoading, runsError, setRuns, setRunsLoading, setRunsError,
          selectedRunIds, toggleRunSelection, clearSelection } = useAppStore()

  const [statusFilter, setStatusFilter] = useState<string>('All')
  const [engineFilter, setEngineFilter] = useState<string>('All')

  const loadRuns = () => {
    setRunsLoading(true)
    setRunsError(null)
    api
      .listRuns()
      .then(({ items }) => {
        setRuns(items)
        setRunsLoading(false)
      })
      .catch((err: Error) => {
        setRunsError(err.message)
        setRunsLoading(false)
      })
  }

  useEffect(() => {
    loadRuns()
    return () => {
      clearSelection()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filtered = runs.filter((r) => {
    if (statusFilter !== 'All' && r.status !== statusFilter) return false
    if (engineFilter !== 'All' && r.engine !== engineFilter) return false
    return true
  })

  const handleCompare = () => {
    navigate(`/compare?ids=${selectedRunIds.join(',')}`)
  }

  const handleRowClick = (e: React.MouseEvent, id: string) => {
    if ((e.target as HTMLElement).closest('[data-no-nav]')) return
    navigate(`/runs/${id}`)
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Benchmark Runs</h1>
        <div className="flex items-center gap-3">
          {selectedRunIds.length >= 2 && (
            <button
              onClick={handleCompare}
              className="bg-white text-indigo-600 px-4 py-2 rounded-lg border border-indigo-300 hover:bg-indigo-50 text-sm font-medium transition-colors"
            >
              Compare selected ({selectedRunIds.length})
            </button>
          )}
          <button
            onClick={() => navigate('/runs/new')}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 text-sm font-medium transition-colors"
          >
            New run
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s === 'All' ? 'All statuses' : s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Engine:</label>
          <select
            value={engineFilter}
            onChange={(e) => setEngineFilter(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          >
            {ENGINE_OPTIONS.map((eng) => (
              <option key={eng} value={eng}>
                {eng === 'All' ? 'All engines' : eng}
              </option>
            ))}
          </select>
        </div>
        {(statusFilter !== 'All' || engineFilter !== 'All') && (
          <button
            onClick={() => {
              setStatusFilter('All')
              setEngineFilter('All')
            }}
            className="text-sm text-gray-500 hover:text-gray-700 underline"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Error banner */}
      {runsError && (
        <div className="mb-4 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <span className="text-sm text-red-700">{runsError}</span>
          <button
            onClick={loadRuns}
            className="text-sm font-medium text-red-700 hover:text-red-900 underline ml-4"
          >
            Retry
          </button>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="w-10 px-4 py-3">
                <span className="sr-only">Select</span>
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Run
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Engine
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Model
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Progress
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Duration
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {runsLoading ? (
              Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-sm text-gray-500">
                  {runs.length === 0
                    ? 'No runs yet. Start your first benchmark run.'
                    : 'No runs match the current filters.'}
                </td>
              </tr>
            ) : (
              filtered.map((run) => {
                const isSelected = selectedRunIds.includes(run.id)
                const pct =
                  run.total_requests > 0
                    ? Math.round((run.completed_requests / run.total_requests) * 100)
                    : 0

                return (
                  <tr
                    key={run.id}
                    onClick={(e) => handleRowClick(e, run.id)}
                    className={`hover:bg-gray-50 cursor-pointer transition-colors ${
                      isSelected ? 'bg-indigo-50' : ''
                    }`}
                  >
                    {/* Checkbox */}
                    <td className="px-4 py-3" data-no-nav="true">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleRunSelection(run.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="w-4 h-4 text-indigo-600 border-gray-300 rounded cursor-pointer"
                        aria-label={`Select run ${run.id.slice(0, 8)}`}
                      />
                    </td>

                    {/* Run ID */}
                    <td className="px-4 py-3">
                      <span className="font-mono text-indigo-600 font-medium">
                        #{run.id.slice(0, 8)}
                      </span>
                    </td>

                    {/* Engine */}
                    <td className="px-4 py-3 font-medium text-gray-900">{run.engine}</td>

                    {/* Model */}
                    <td className="px-4 py-3">
                      <span
                        className="text-gray-700 max-w-xs truncate block"
                        title={run.model}
                      >
                        {run.model}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>

                    {/* Progress */}
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1 min-w-[96px]">
                        <span className="text-xs text-gray-600">
                          {run.completed_requests}/{run.total_requests}
                        </span>
                        {run.total_requests > 0 && (
                          <div className="w-24 bg-gray-200 rounded-full h-1.5">
                            <div
                              className="bg-indigo-500 h-1.5 rounded-full transition-all"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Duration */}
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                      {formatDuration(run.started_at, run.completed_at)}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3" data-no-nav="true">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          navigate(`/runs/${run.id}`)
                        }}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Footer count */}
      {!runsLoading && !runsError && filtered.length > 0 && (
        <p className="mt-3 text-xs text-gray-500">
          Showing {filtered.length} of {runs.length} run{runs.length !== 1 ? 's' : ''}
          {selectedRunIds.length > 0 && ` · ${selectedRunIds.length} selected`}
        </p>
      )}
    </div>
  )
}
