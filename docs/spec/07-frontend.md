# Inference Benchrunner — Frontend Pages

## Stack
React 18 + TypeScript, Vite, Zustand, Tailwind CSS, Recharts.
Phase 1: Vite dev server. Phase 2: nginx serving built static files.

## Error handling
All API errors: inline error banner with message + retry button.
No full-page error states in Phase 1.

## Run list (home page)
Table columns: name, engine, model, status badge, duration, avg p99, avg tok/s.
Filters: status, project, engine, tag.
Click row → run detail. Button: "New run".

## New run wizard

### Step 1 — Select suite
Browse prompt library, preview prompts, select suite or create inline.

### Step 2 — Configure engine
UI order within step:
1. Engine selector (ollama | llamacpp | vllm | sglang)
2. Local/remote toggle
3. Host input (shown if remote)
4. Port input
5. "Refresh models" button → GET /api/engines/{engine}/models?host={host}
   (reads from DB registry — does not call live engine)
6. Model picker (populated after refresh; for llamacpp shows text input)
7. Concurrency slider
8. Temperature / max_tokens inputs
9. spawn_mode selector: "Managed" (agent spawns engine) | "Attach" (connect to existing)
   For Ollama: selector is hidden, spawn_mode locked to "attach", note displayed:
   "Ollama runs as a system service — always attach mode."

### Step 3 — Advanced
Warmup rounds, auto-retry, request timeout (seconds), watchdog interval (seconds, default 10), variable overrides,
notes, tags, project assignment.

### Step 4 — Review + launch
Summary card of all settings. "Start run" button.

## Run detail page
- Status badge + live progress bar (WebSocket /ws/runs/{id})
- Run timeline: started_at → warmup_duration_ms → run_started_at → completed_at
- Real-time tok/sec, TTFT, error rate, server health indicator (2s refresh via WebSocket server_alive field)
- Request log table: last 20 requests, paginated
- Cancel button (visible only when status = "running")
- Grafana deep-link: `{GRAFANA_URL}/d/bench-dashboard/bench?var-run_id={run_id}`
  (dashboard UID fixed as "bench-dashboard" in provisioned JSON)

## Compare page

### Phase 1
- Multi-select runs from run history
- Metric toggle: p99 / TTFT / throughput
- Chart: Recharts BarChart — one bar per run, grouped by metric
  Data source: POST /api/runs/compare (aggregate stats only)
- Confidence bands shown as error bars (±1 std dev) on each bar
- TPS source indicator per run: "engine-reported" (Ollama/llamacpp) vs
  "wall-clock" (vLLM/SGLang) — tooltip on metric card
- Summary scorecard table: avg, p99, min, max, σ per run
- "Save comparison" button → names it + generates shareable URL
- Export: PNG chart, CSV data (Phase 2)

### Phase 2 — time-series LineChart
- Replace BarChart with Recharts LineChart
- Requires new endpoint: GET /api/runs/{id}/timeseries?metric=p99&bucket_s=10
  Backend bins RequestRecord rows by time bucket relative to run_started_at,
  returns aggregated series for charting
- X axis: relative seconds since run_started_at (NOT wall-clock time)
- One line per run, coloured by run; confidence bands toggle on/off

## Prompt library
Grid of prompt cards, filterable by category.
Create / edit / delete prompts.
Import CSV (columns: name, content, category, variable_key=default_value...).
Suite builder: drag prompts into ordered list, save as suite.

## Projects
List with run count + last run date.
Click → filtered run list for that project.

## Model registry page

Browse all known models across all engines and hosts.
Filter by engine, host.
Columns: engine, host, model_id, display_name, source (synced/manual), last_synced, notes.

Actions per row:
- Edit display_name and notes
- Delete from registry

"Sync models" button per engine+host:
- Requires engine to be running at host:port
- Calls POST /api/engines/{engine}/models/sync
- Shows diff: new models found, models no longer present (marked stale, not deleted)

"Add model" button:
- Manual entry form: engine, host, model_id, display_name, notes
- Always source="manual"
- Required for llamacpp (no discovery API)

### Stale model handling
When a sync runs and a previously-synced model is no longer returned by the engine:
- Model is NOT deleted from registry automatically
- model is marked stale: last_synced timestamp becomes old
- UI shows a "stale" badge on the row
- User decides whether to keep or delete it
