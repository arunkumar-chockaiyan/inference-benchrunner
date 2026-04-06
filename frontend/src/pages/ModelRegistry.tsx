import { useEffect, useState } from 'react'
import { api, EngineModelRead, EngineMeta } from '../api'

const ENGINE_COLORS: Record<string, string> = {
  ollama: 'bg-green-100 text-green-800',
  llamacpp: 'bg-blue-100 text-blue-800',
  vllm: 'bg-purple-100 text-purple-800',
  sglang: 'bg-orange-100 text-orange-800',
}

function formatDate(s: string | null): string {
  if (!s) return '—'
  return new Date(s).toLocaleString()
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s
  return s.slice(0, n) + '…'
}

function SkeletonRow() {
  return (
    <tr className="border-b border-gray-100">
      {Array.from({ length: 8 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div
            className="h-4 bg-gray-200 rounded animate-pulse"
            style={{ width: i === 0 ? '60px' : i === 7 ? '40px' : '80%' }}
          />
        </td>
      ))}
    </tr>
  )
}

interface SyncModalProps {
  engines: EngineMeta[]
  onClose: () => void
  onSuccess: () => void
}

function SyncModal({ engines, onClose, onSuccess }: SyncModalProps) {
  const [engine, setEngine] = useState(engines[0]?.name ?? 'ollama')
  const [host, setHost] = useState('localhost')
  const [port, setPort] = useState<number>(engines[0]?.default_port ?? 11434)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleEngineChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value
    setEngine(name)
    const meta = engines.find((en) => en.name === name)
    if (meta) setPort(meta.default_port)
    setResult(null)
    setError(null)
  }

  const handleSync = () => {
    setLoading(true)
    setResult(null)
    setError(null)
    api
      .syncEngineModels(engine, host, port)
      .then(({ synced }) => {
        setResult(`Synced ${synced} model${synced !== 1 ? 's' : ''}`)
        setLoading(false)
      })
      .catch((err: Error) => {
        const msg = err.message
        if (msg.toLowerCase().includes('does not support model listing') || msg.toLowerCase().includes('not support')) {
          setResult(msg)
        } else {
          setError(msg)
        }
        setLoading(false)
      })
  }

  const handleSuccessClose = () => {
    onSuccess()
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Sync Models</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Engine</label>
            <select
              value={engine}
              onChange={handleEngineChange}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {engines.map((en) => (
                <option key={en.name} value={en.name}>
                  {en.display_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Host</label>
            <input
              type="text"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="localhost"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Port</label>
            <input
              type="number"
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-4 bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-sm text-green-800">
            {result}
          </div>
        )}

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
          >
            {result ? 'Close' : 'Cancel'}
          </button>
          {result && !error ? (
            <button
              onClick={handleSuccessClose}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              Done
            </button>
          ) : (
            <button
              onClick={handleSync}
              disabled={loading}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 transition-colors"
            >
              {loading ? 'Syncing…' : 'Sync'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

interface AddModalProps {
  engines: EngineMeta[]
  onClose: () => void
  onAdded: (model: EngineModelRead) => void
}

function AddModal({ engines, onClose, onAdded }: AddModalProps) {
  const [engine, setEngine] = useState(engines[0]?.name ?? 'ollama')
  const [host, setHost] = useState('localhost')
  const [modelId, setModelId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = () => {
    if (!modelId.trim()) {
      setError('Model ID is required')
      return
    }
    setLoading(true)
    setError(null)
    api
      .addEngineModel(engine, {
        engine,
        host,
        model_id: modelId.trim(),
        display_name: displayName.trim(),
        notes: notes.trim(),
      })
      .then((model) => {
        onAdded(model)
        onClose()
      })
      .catch((err: Error) => {
        if (err.message.includes('409') || err.message.toLowerCase().includes('already exists') || err.message.toLowerCase().includes('conflict')) {
          setError('Model already exists')
        } else {
          setError(err.message)
        }
        setLoading(false)
      })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Add Model</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Engine</label>
            <select
              value={engine}
              onChange={(e) => setEngine(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {engines.map((en) => (
                <option key={en.name} value={en.name}>
                  {en.display_name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Host</label>
            <input
              type="text"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="localhost"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Model ID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="e.g. llama3:8b"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Display Name <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Human-friendly name"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Notes <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {loading ? 'Adding…' : 'Add Model'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ModelRegistry() {
  const [engines, setEngines] = useState<EngineMeta[]>([])
  const [models, setModels] = useState<EngineModelRead[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const [engineFilter, setEngineFilter] = useState<string>('All')
  const [hostFilter, setHostFilter] = useState<string>('')

  const [showSync, setShowSync] = useState(false)
  const [showAdd, setShowAdd] = useState(false)

  const loadModels = (engineList: EngineMeta[]) => {
    setLoading(true)
    setError(null)
    Promise.all(engineList.map((en) => api.listEngineModels(en.name)))
      .then((results) => {
        const all = results.flatMap((r) => r.items)
        all.sort((a, b) => {
          if (a.engine !== b.engine) return a.engine.localeCompare(b.engine)
          if (a.host !== b.host) return a.host.localeCompare(b.host)
          return a.model_id.localeCompare(b.model_id)
        })
        setModels(all)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }

  const loadAll = () => {
    setLoading(true)
    setError(null)
    api
      .listEngines()
      .then(({ engines: list }) => {
        setEngines(list)
        loadModels(list)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleDelete = (row: EngineModelRead) => {
    if (!window.confirm(`Delete ${row.model_id}?`)) return
    setDeleteError(null)
    api
      .deleteEngineModel(row.engine, row.id)
      .then(() => {
        setModels((prev) => prev.filter((m) => m.id !== row.id))
      })
      .catch((err: Error) => {
        setDeleteError(err.message)
      })
  }

  const filtered = models.filter((m) => {
    if (engineFilter !== 'All' && m.engine !== engineFilter) return false
    if (hostFilter && !m.host.toLowerCase().includes(hostFilter.toLowerCase())) return false
    return true
  })

  const engineOptions = ['All', ...engines.map((en) => en.name)]

  return (
    <div className="max-w-7xl mx-auto">
      {showSync && (
        <SyncModal
          engines={engines}
          onClose={() => setShowSync(false)}
          onSuccess={() => loadAll()}
        />
      )}
      {showAdd && (
        <AddModal
          engines={engines}
          onClose={() => setShowAdd(false)}
          onAdded={(model) => {
            setModels((prev) => {
              const next = [...prev, model]
              next.sort((a, b) => {
                if (a.engine !== b.engine) return a.engine.localeCompare(b.engine)
                if (a.host !== b.host) return a.host.localeCompare(b.host)
                return a.model_id.localeCompare(b.model_id)
              })
              return next
            })
          }}
        />
      )}

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Model Registry</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSync(true)}
            className="bg-white text-indigo-600 px-4 py-2 rounded-lg border border-indigo-300 hover:bg-indigo-50 text-sm font-medium transition-colors"
          >
            Sync models
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 text-sm font-medium transition-colors"
          >
            Add model
          </button>
        </div>
      </div>

      <div className="flex items-center gap-4 mb-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Engine:</label>
          <div className="flex items-center gap-1">
            {engineOptions.map((opt) => (
              <button
                key={opt}
                onClick={() => setEngineFilter(opt)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  engineFilter === opt
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Host:</label>
          <input
            type="text"
            value={hostFilter}
            onChange={(e) => setHostFilter(e.target.value)}
            placeholder="Filter by host…"
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-48"
          />
          {hostFilter && (
            <button
              onClick={() => setHostFilter('')}
              className="text-sm text-gray-500 hover:text-gray-700 underline"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <span className="text-sm text-red-700">{error}</span>
          <button
            onClick={loadAll}
            className="text-sm font-medium text-red-700 hover:text-red-900 underline ml-4"
          >
            Retry
          </button>
        </div>
      )}

      {deleteError && (
        <div className="mb-4 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <span className="text-sm text-red-700">{deleteError}</span>
          <button
            onClick={() => setDeleteError(null)}
            className="text-sm font-medium text-red-700 hover:text-red-900 underline ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Engine
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Host
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Model ID
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Display Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Source
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Last Synced
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Notes
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-sm text-gray-500">
                  {models.length === 0
                    ? 'No models registered yet. Sync or add a model to get started.'
                    : 'No models match the current filters.'}
                </td>
              </tr>
            ) : (
              filtered.map((row) => (
                <tr key={row.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                        ENGINE_COLORS[row.engine] ?? 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {row.engine}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{row.host}</td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-gray-900 text-xs">{row.model_id}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{row.display_name || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                          row.source === 'manual'
                            ? 'bg-indigo-100 text-indigo-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {row.source}
                      </span>
                      {row.is_stale && (
                        <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
                          stale
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap text-xs">
                    {formatDate(row.last_synced)}
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs">
                    {row.notes ? (
                      <span title={row.notes}>{truncate(row.notes, 40)}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => void handleDelete(row)}
                      className="text-xs text-red-600 hover:text-red-800 font-medium"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && !error && filtered.length > 0 && (
        <p className="mt-3 text-xs text-gray-500">
          Showing {filtered.length} of {models.length} model{models.length !== 1 ? 's' : ''}
        </p>
      )}
    </div>
  )
}
