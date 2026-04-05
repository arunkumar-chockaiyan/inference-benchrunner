import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, EngineModelRead, RunCreate, SuiteRead } from '../api'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENGINES = ['ollama', 'llamacpp', 'vllm', 'sglang'] as const
type Engine = (typeof ENGINES)[number]

const DEFAULT_PORTS: Record<Engine, number> = {
  ollama: 11434,
  llamacpp: 8080,
  vllm: 8000,
  sglang: 30000,
}

// ---------------------------------------------------------------------------
// Step indicator
// ---------------------------------------------------------------------------

function StepIndicator({ current }: { current: number }) {
  const steps = ['Select suite', 'Engine', 'Advanced', 'Review']
  return (
    <div className="flex items-center justify-center mb-8">
      {steps.map((label, i) => {
        const step = i + 1
        const done = step < current
        const active = step === current
        return (
          <div key={step} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                  done
                    ? 'bg-indigo-600 text-white'
                    : active
                      ? 'bg-indigo-600 text-white ring-4 ring-indigo-100'
                      : 'bg-gray-200 text-gray-500'
                }`}
              >
                {done ? '✓' : step}
              </div>
              <span
                className={`mt-1 text-xs whitespace-nowrap ${
                  active ? 'text-indigo-600 font-medium' : 'text-gray-500'
                }`}
              >
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className={`h-0.5 w-16 mx-1 mb-4 transition-colors ${
                  done ? 'bg-indigo-600' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// NewRunWizard
// ---------------------------------------------------------------------------

export default function NewRunWizard() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)

  // --- Step 1 state ---
  const [suites, setSuites] = useState<SuiteRead[]>([])
  const [suitesLoading, setSuitesLoading] = useState(false)
  const [selectedSuiteId, setSelectedSuiteId] = useState<string | null>(null)

  // --- Step 2 state ---
  const [engine, setEngine] = useState<Engine>('ollama')
  const [isRemote, setIsRemote] = useState(false)
  const [host, setHost] = useState('localhost')
  const [port, setPort] = useState<number>(11434)
  const [models, setModels] = useState<EngineModelRead[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState('')
  const [llamacppModelPath, setLlamacppModelPath] = useState('')
  const [concurrency, setConcurrency] = useState(1)
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(512)
  const [spawnMode, setSpawnMode] = useState<'managed' | 'attach'>('attach')
  const [runName, setRunName] = useState('')

  // --- Step 3 state ---
  const [warmupRounds, setWarmupRounds] = useState(3)
  const [autoRetry, setAutoRetry] = useState(2)
  const [requestTimeout, setRequestTimeout] = useState(120)
  const [watchdogInterval, setWatchdogInterval] = useState(10)
  const [notes, setNotes] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')

  // --- Step 4 state ---
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Load suites on mount
  useEffect(() => {
    setSuitesLoading(true)
    api
      .listSuites()
      .then(({ items }) => setSuites(items))
      .catch(() => {})
      .finally(() => setSuitesLoading(false))
  }, [])

  // Update port when engine changes
  useEffect(() => {
    setPort(DEFAULT_PORTS[engine])
    setSelectedModel('')
    setModels([])
    if (engine === 'ollama') setSpawnMode('attach')
  }, [engine])

  // Auto-generate run name
  useEffect(() => {
    const model = engine === 'llamacpp' ? llamacppModelPath : selectedModel
    setRunName(`${engine}-${model || 'model'}-${Date.now().toString(36)}`)
  }, [engine, selectedModel, llamacppModelPath])

  const handleRefreshModels = () => {
    setModelsLoading(true)
    setModelsError(null)
    api
      .listEngineModels(engine, isRemote ? host : 'localhost')
      .then(({ items }) => setModels(items))
      .catch((e: Error) => setModelsError(e.message))
      .finally(() => setModelsLoading(false))
  }

  const handleTagKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && tagInput.trim()) {
      e.preventDefault()
      setTags((prev) => [...new Set([...prev, tagInput.trim()])])
      setTagInput('')
    }
  }

  const handleSubmit = async () => {
    if (!selectedSuiteId) return
    setSubmitting(true)
    setSubmitError(null)
    const model = engine === 'llamacpp' ? llamacppModelPath : selectedModel
    const body: RunCreate = {
      name: runName,
      engine,
      model,
      suite_id: selectedSuiteId,
      host: isRemote ? host : 'localhost',
      port,
      spawn_mode: spawnMode,
      concurrency,
      temperature,
      max_tokens: maxTokens,
      warmup_rounds: warmupRounds,
      auto_retry: autoRetry,
      request_timeout_s: requestTimeout,
      watchdog_interval_s: watchdogInterval,
      notes,
      tags,
    }
    try {
      const run = await api.createRun(body)
      navigate(`/runs/${run.id}`)
    } catch (e: unknown) {
      setSubmitError((e as Error).message)
      setSubmitting(false)
    }
  }

  const selectedSuite = suites.find((s) => s.id === selectedSuiteId)

  // ---------------------------------------------------------------------------
  // Render steps
  // ---------------------------------------------------------------------------

  const renderStep1 = () => (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Select a prompt suite</h2>
      {suitesLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : suites.length === 0 ? (
        <p className="text-sm text-gray-500 py-8 text-center">
          No suites found. Create a prompt suite first.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {suites.map((suite) => (
            <button
              key={suite.id}
              onClick={() => setSelectedSuiteId(suite.id)}
              className={`text-left p-4 rounded-lg border-2 transition-colors ${
                selectedSuiteId === suite.id
                  ? 'border-indigo-500 bg-indigo-50'
                  : 'border-gray-200 bg-white hover:border-indigo-300'
              }`}
            >
              <div className="font-medium text-gray-900">{suite.name}</div>
              {suite.description && (
                <div className="text-sm text-gray-500 mt-1 line-clamp-2">{suite.description}</div>
              )}
              <div className="text-xs text-gray-400 mt-2">
                {suite.prompt_ids.length} prompt{suite.prompt_ids.length !== 1 ? 's' : ''}
                {' · '}v{suite.version}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )

  const renderStep2 = () => (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold text-gray-900">Configure engine</h2>

      {/* Engine selector */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Engine</label>
        <div className="flex gap-2 flex-wrap">
          {ENGINES.map((eng) => (
            <button
              key={eng}
              onClick={() => setEngine(eng)}
              className={`px-4 py-2 rounded-lg border text-sm font-medium transition-colors ${
                engine === eng
                  ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                  : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              {eng}
            </button>
          ))}
        </div>
      </div>

      {/* Local / Remote toggle */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Location</label>
        <div className="flex rounded-lg overflow-hidden border border-gray-300 w-fit">
          <button
            onClick={() => { setIsRemote(false); setHost('localhost') }}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              !isRemote ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            Local
          </button>
          <button
            onClick={() => setIsRemote(true)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-l border-gray-300 ${
              isRemote ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            Remote
          </button>
        </div>
      </div>

      {/* Host (remote only) */}
      {isRemote && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Host</label>
          <input
            type="text"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="100.x.x.x or hostname.ts.net"
            className="w-full max-w-sm px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
      )}

      {/* Port */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Port</label>
        <input
          type="number"
          value={port}
          onChange={(e) => setPort(Number(e.target.value))}
          className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
        />
      </div>

      {/* Model */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-sm font-medium text-gray-700">Model</label>
          {engine !== 'llamacpp' && (
            <button
              onClick={handleRefreshModels}
              disabled={modelsLoading}
              className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
            >
              {modelsLoading ? 'Loading…' : '↻ Refresh models'}
            </button>
          )}
        </div>
        {engine === 'llamacpp' ? (
          <input
            type="text"
            value={llamacppModelPath}
            onChange={(e) => setLlamacppModelPath(e.target.value)}
            placeholder="/path/to/model.gguf"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        ) : (
          <>
            {modelsError && (
              <p className="text-xs text-red-600 mb-1">{modelsError}</p>
            )}
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm bg-white"
              disabled={models.length === 0}
            >
              <option value="">
                {models.length === 0 ? '— click Refresh models —' : '— select model —'}
              </option>
              {models.map((m) => (
                <option key={m.id} value={m.model_id}>
                  {m.display_name || m.model_id}
                  {m.is_stale ? ' (stale)' : ''}
                </option>
              ))}
            </select>
          </>
        )}
      </div>

      {/* Concurrency */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Concurrency: {concurrency}
        </label>
        <input
          type="range"
          min={1}
          max={32}
          value={concurrency}
          onChange={(e) => setConcurrency(Number(e.target.value))}
          className="w-48"
        />
      </div>

      {/* Temperature + max tokens */}
      <div className="flex gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Temperature</label>
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
            className="w-28 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Max tokens</label>
          <input
            type="number"
            min={1}
            value={maxTokens}
            onChange={(e) => setMaxTokens(Number(e.target.value))}
            className="w-28 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
      </div>

      {/* Spawn mode */}
      {engine !== 'ollama' ? (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Spawn mode</label>
          <div className="flex rounded-lg overflow-hidden border border-gray-300 w-fit">
            <button
              onClick={() => setSpawnMode('attach')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                spawnMode === 'attach' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              Attach
            </button>
            <button
              onClick={() => setSpawnMode('managed')}
              className={`px-4 py-2 text-sm font-medium border-l border-gray-300 transition-colors ${
                spawnMode === 'managed' ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              Managed
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {spawnMode === 'attach'
              ? 'Connect to an already-running engine.'
              : 'Agent will spawn the engine process.'}
          </p>
        </div>
      ) : (
        <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          Ollama runs as a system service — always attach mode.
        </div>
      )}

      {/* Run name */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Run name</label>
        <input
          type="text"
          value={runName}
          onChange={(e) => setRunName(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
        />
      </div>
    </div>
  )

  const renderStep3 = () => (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold text-gray-900">Advanced settings</h2>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Warmup rounds</label>
          <input
            type="number"
            min={0}
            value={warmupRounds}
            onChange={(e) => setWarmupRounds(Number(e.target.value))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Auto-retry</label>
          <input
            type="number"
            min={0}
            max={10}
            value={autoRetry}
            onChange={(e) => setAutoRetry(Number(e.target.value))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Request timeout (s)</label>
          <input
            type="number"
            min={5}
            value={requestTimeout}
            onChange={(e) => setRequestTimeout(Number(e.target.value))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Watchdog interval (s)</label>
          <input
            type="number"
            min={5}
            value={watchdogInterval}
            onChange={(e) => setWatchdogInterval(Number(e.target.value))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Any notes about this run..."
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm resize-none"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Tags</label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full text-xs"
            >
              {tag}
              <button
                onClick={() => setTags((prev) => prev.filter((t) => t !== tag))}
                className="hover:text-indigo-900 font-bold leading-none"
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <input
          type="text"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={handleTagKeyDown}
          placeholder="Type and press Enter to add a tag"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
        />
      </div>
    </div>
  )

  const renderStep4 = () => {
    const model = engine === 'llamacpp' ? llamacppModelPath : selectedModel
    const rows = [
      ['Run name', runName],
      ['Suite', selectedSuite?.name ?? selectedSuiteId ?? '—'],
      ['Engine', engine],
      ['Model', model || '—'],
      ['Host', `${isRemote ? host : 'localhost'}:${port}`],
      ['Spawn mode', spawnMode],
      ['Concurrency', String(concurrency)],
      ['Temperature', String(temperature)],
      ['Max tokens', String(maxTokens)],
      ['Warmup rounds', String(warmupRounds)],
      ['Auto-retry', String(autoRetry)],
      ['Request timeout', `${requestTimeout}s`],
      ['Tags', tags.length > 0 ? tags.join(', ') : '—'],
    ]
    return (
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Review & launch</h2>
        <div className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-gray-200">
              {rows.map(([label, value]) => (
                <tr key={label}>
                  <td className="px-4 py-2.5 font-medium text-gray-600 w-40">{label}</td>
                  <td className="px-4 py-2.5 text-gray-900">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {submitError && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {submitError}
          </div>
        )}
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="w-full bg-indigo-600 text-white py-2.5 rounded-lg hover:bg-indigo-700 disabled:opacity-50 font-medium transition-colors"
        >
          {submitting ? 'Starting run…' : '▶ Start run'}
        </button>
      </div>
    )
  }

  // Validate step before advancing
  const canAdvance = () => {
    if (step === 1) return selectedSuiteId !== null
    if (step === 2) {
      const model = engine === 'llamacpp' ? llamacppModelPath : selectedModel
      return model.trim() !== '' && runName.trim() !== ''
    }
    return true
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/')}
          className="text-gray-500 hover:text-gray-700 text-sm"
        >
          ← Back to runs
        </button>
        <h1 className="text-xl font-semibold text-gray-900">New benchmark run</h1>
      </div>

      <StepIndicator current={step} />

      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
        {step === 4 && renderStep4()}
      </div>

      {step < 4 && (
        <div className="flex justify-between">
          <button
            onClick={() => setStep((s) => s - 1)}
            disabled={step === 1}
            className="bg-white text-gray-700 px-5 py-2 rounded-lg border border-gray-300 hover:bg-gray-50 disabled:opacity-40 text-sm font-medium transition-colors"
          >
            Back
          </button>
          <button
            onClick={() => setStep((s) => s + 1)}
            disabled={!canAdvance()}
            className="bg-indigo-600 text-white px-5 py-2 rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium transition-colors"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
