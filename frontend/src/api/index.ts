const BASE = '/api'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail?: string }).detail ?? res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RunSummary {
  id: string
  config_id: string
  status: 'pending' | 'starting' | 'warming_up' | 'running' | 'completed' | 'failed' | 'cancelled'
  total_requests: number
  completed_requests: number
  failed_requests: number
  started_at: string | null
  completed_at: string | null
  engine: string
  model: string
  host: string
}

export interface RunConfigRead {
  id: string
  name: string
  engine: string
  model: string
  host: string
  port: number
  agent_port: number
  spawn_mode: string
  concurrency: number
  temperature: number
  max_tokens: number
  top_p: number
  request_timeout_s: number
  warmup_rounds: number
  auto_retry: number
  variable_overrides: Record<string, string>
  notes: string
  tags: string[]
}

export interface RunRead {
  id: string
  config_id: string
  status: string
  total_requests: number
  completed_requests: number
  failed_requests: number
  started_at: string | null
  warmup_duration_ms: number | null
  run_started_at: string | null
  completed_at: string | null
  error_message: string | null
  server_owned: boolean
  server_pid: number | null
  sidecar_pid: number | null
  cleanup_warning: string | null
  config: RunConfigRead
}

export interface RunCreate {
  name: string
  engine: string
  model: string
  suite_id: string
  host?: string
  port: number
  agent_port?: number
  spawn_mode?: string
  health_timeout_s?: number
  concurrency?: number
  temperature?: number
  max_tokens?: number
  top_p?: number
  request_timeout_s?: number
  watchdog_interval_s?: number
  warmup_rounds?: number
  auto_retry?: number
  variable_overrides?: Record<string, string>
  notes?: string
  tags?: string[]
  project_id?: string | null
}

export interface SuiteRead {
  id: string
  name: string
  description: string
  version: number
  prompt_ids: string[]
  created_at: string
  updated_at: string
}

export interface PromptRead {
  id: string
  name: string
  content: string
  category: string
  variables: Record<string, string>
  created_at: string
  updated_at: string
}

export interface EngineModelRead {
  id: string
  engine: string
  model_id: string
  display_name: string
  source: string
  is_stale: boolean
  last_synced: string | null
  notes: string
}

export interface RunStats {
  run_id: string
  engine: string
  model: string
  avg_latency_ms: number | null
  p50_latency_ms: number | null
  p99_latency_ms: number | null
  min_latency_ms: number | null
  max_latency_ms: number | null
  stddev_latency_ms: number | null
  avg_ttft_ms: number | null
  p50_ttft_ms: number | null
  p99_ttft_ms: number | null
  avg_tokens_per_sec: number | null
  total_requests: number
  failed_requests: number
  sample_count: number
}

export interface WsEvent {
  run_id: string
  status: string
  completed: number
  total: number
  failed: number
  current_tps: number | null
  elapsed_seconds: number
  eta_seconds: number | null
  server_alive: boolean
}

export interface ProjectRead {
  id: string
  name: string
  description: string
  created_at: string
}

export interface PromptCreate {
  name: string
  content: string
  category: string
  variables: Record<string, string>
}

export interface PromptUpdate {
  name?: string
  content?: string
  category?: string
  variables?: Record<string, string>
}

export interface SuiteCreate {
  name: string
  description: string
  prompt_ids: string[]
}

export interface SuiteUpdate {
  name?: string
  description?: string
  prompt_ids?: string[]
}

export interface EngineModelCreate {
  engine: string
  model_id: string
  display_name: string
  notes: string
}

export interface EngineMeta {
  name: string
  display_name: string
  spawn_modes: string[]
  default_port: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildQuery(params?: Record<string, string | number | undefined | null>): string {
  if (!params) return ''
  const q = Object.entries(params)
    .filter(([, v]) => v != null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&')
  return q ? `?${q}` : ''
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const api = {
  // Runs
  listRuns: (params?: { status?: string; engine?: string; cursor?: string; limit?: number }) =>
    request<{ items: RunSummary[]; next_cursor: string | null }>('GET', '/runs' + buildQuery(params)),

  getRun: (id: string) =>
    request<RunRead>('GET', `/runs/${id}`),

  createRun: (body: RunCreate) =>
    request<RunRead>('POST', '/runs', body),

  cancelRun: (id: string) =>
    request<void>('DELETE', `/runs/${id}`),

  compareRuns: (run_ids: string[], metric: string) =>
    request<{ runs: RunStats[] }>('POST', '/runs/compare', { run_ids, metric }),

  // Suites
  listSuites: () =>
    request<{ items: SuiteRead[] }>('GET', '/suites'),

  getSuite: (id: string) =>
    request<SuiteRead>('GET', `/suites/${id}`),

  createSuite: (body: SuiteCreate) =>
    request<SuiteRead>('POST', '/suites', body),

  updateSuite: (id: string, body: SuiteUpdate) =>
    request<SuiteRead>('PUT', `/suites/${id}`, body),

  deleteSuite: (id: string) =>
    request<void>('DELETE', `/suites/${id}`),

  // Prompts
  listPrompts: (params?: { category?: string; cursor?: string }) =>
    request<{ items: PromptRead[]; next_cursor: string | null }>(
      'GET',
      '/prompts' + buildQuery(params),
    ),

  createPrompt: (body: PromptCreate) =>
    request<PromptRead>('POST', '/prompts', body),

  updatePrompt: (id: string, body: PromptUpdate) =>
    request<PromptRead>('PUT', `/prompts/${id}`, body),

  deletePrompt: (id: string) =>
    request<void>('DELETE', `/prompts/${id}`),

  // Engines
  listEngines: () =>
    request<{ engines: EngineMeta[] }>('GET', '/engines'),

  listEngineModels: (engine: string) =>
    request<{ items: EngineModelRead[] }>('GET', `/engines/${engine}/models`),

  syncEngineModels: (engine: string, host: string, port: number) =>
    request<{ synced: number }>(
      'POST',
      `/engines/${engine}/models/sync?host=${encodeURIComponent(host)}&port=${port}`,
    ),

  addEngineModel: (engine: string, body: EngineModelCreate) =>
    request<EngineModelRead>('POST', `/engines/${engine}/models`, body),

  deleteEngineModel: (engine: string, modelId: string) =>
    request<void>('DELETE', `/engines/${engine}/models/${modelId}`),

  // Projects
  listProjects: () =>
    request<{ items: ProjectRead[] }>('GET', '/projects'),

  createProject: (body: { name: string; description?: string }) =>
    request<ProjectRead>('POST', '/projects', body),

  listProjectRuns: (id: string) =>
    request<{ items: RunSummary[] }>('GET', `/projects/${id}/runs`),
}
