# QA Spec — Frontend

Source: `docs/spec/07-frontend.md`, `frontend/src/`

Framework: React 18 + TypeScript, Vite, Zustand, Tailwind CSS, Recharts.
Testing: Vitest + React Testing Library for unit/component; Playwright for E2E flows.

---

## Run list page

### Rendering

- Columns displayed: name, engine, model, status badge, duration, avg p99, avg tok/s
- Empty state: shown when no runs exist (no crash, no blank page)
- Each row is clickable → navigates to run detail page

### Filters

| Filter | Interaction | Expected |
|--------|-------------|---------|
| Status | Select "completed" | Only completed runs shown |
| Engine | Select "vllm" | Only vllm runs shown |
| Tag | Enter "gpu-test" | Runs with that tag shown |
| Project | Select project | Runs for that project shown |
| Clear filter | Reset | All runs shown |

### Status badge colours

Assert correct badge rendered per status:
- `pending` → neutral
- `running` → active/animated
- `completed` → success (green)
- `failed` → error (red)
- `cancelled` → warning (yellow)

---

## New run wizard

### Step 1 — Select suite

- Prompt library grid renders
- Category filter works
- Prompt preview shows `content` field
- Selecting a suite enables "Next" button
- "Create inline" opens suite builder
- Suite builder: prompts draggable into ordered list

### Step 2 — Configure engine

**UI field order** (tested via DOM order, not just presence):
1. Engine selector
2. Local/remote toggle
3. Host input (hidden when local, visible when remote)
4. Port input
5. "Refresh models" button
6. Model picker
7. Concurrency slider
8. Temperature / max_tokens inputs
9. spawn_mode selector

**Engine-specific rules:**

| Engine | spawn_mode selector | Note shown |
|--------|---------------------|-----------|
| Ollama | Hidden | "Ollama runs as a system service — always attach mode." |
| Others | Visible (Managed / Attach) | — |

**"Refresh models" button:**
- Calls `GET /api/engines/{engine}/models?host={host}` (DB registry, not live engine)
- llamacpp: shows text input instead of picker
- Populated list: model picker shows options
- Empty list: picker shows "No models — add manually"

### Step 3 — Advanced

Fields present: warmup_rounds, auto_retry, request_timeout_s, watchdog_interval_s (default 10),
variable_overrides, notes, tags, project assignment.

### Step 4 — Review + launch

- Summary card shows all settings from steps 1–3
- "Start run" calls `POST /api/runs`
- `validate_config()` fails → inline error list shown (not full-page error)
- Success → navigate to run detail page

### Wizard navigation

- "Back" on step 2 preserves step 1 selection
- "Back" on step 3 preserves step 2 values
- Completing step 4 does not lose any earlier selections

---

## Run detail page

### Static fields

- Run name, engine, model, status badge
- Timeline: `started_at` → warmup duration → `run_started_at` → `completed_at`
- Grafana deep-link: `{GRAFANA_URL}/d/bench-dashboard/bench?var-run_id={run_id}`
  - Assert link present and `var-run_id` uses exact run UUID

### Live progress (WebSocket)

- Connects to `WS /ws/runs/{id}` on page mount
- Progress bar updates from WebSocket events (`completed / total`)
- Real-time display: tok/sec, TTFT, error rate, elapsed, ETA
- `server_alive: false` → server health indicator shows warning
- On terminal state event (code 1000): progress bar freezes, cancel button hidden
- On unexpected close (code ≠ 1000): client reconnects with exponential backoff

### Cancel button

- Visible only when `status = "running"`
- Calls `DELETE /api/runs/{id}`
- `409` response (terminal state): button disabled, error banner shown
- After successful cancel: status badge updates to "cancelled"

### Request log table

- Shows last 20 requests, paginated
- Columns: attempt, status, TTFT ms, latency ms, tokens, tok/s
- Error rows highlighted

---

## Compare page

### Run selection

- Multi-select from run history
- Metric toggle: p99 / TTFT / throughput

### Chart (Phase 1 — BarChart)

- One bar per run
- Error bars show ±1 std dev (confidence band)
- Chart data sourced from `POST /api/runs/compare`
- TPS source indicator tooltip: "engine-reported" (Ollama/llamacpp) vs "wall-clock" (vLLM/SGLang)

### Summary scorecard table

Columns: avg, p99, min, max, σ per run. Verify all values present.

### Save comparison

- "Save comparison" button → name input → calls `POST /api/comparisons`
- Success → shareable URL displayed containing the `token`

---

## Prompt library page

- Grid of prompt cards, filterable by category
- Create / edit / delete prompts
- Import CSV: columns `name, content, category, variable_key=default_value...`
- Suite builder: drag prompts into ordered list, save as suite

---

## Model registry page

### Table columns

engine, host, model_id, display_name, source (synced/manual), last_synced, notes.

### Actions

| Action | Expected |
|--------|---------|
| Edit display_name | PUT to update; table refreshes |
| Edit notes | PUT to update |
| Delete | Removed from table |

### Sync models button

- Requires engine running at host:port
- Calls `POST /api/engines/{engine}/models/sync`
- Shows diff: new / stale models
- Stale models: "stale" badge rendered, not auto-deleted

### Add model (manual)

- Form: engine, host, model_id, display_name, notes
- Always creates with `source="manual"`
- Required for llamacpp

---

## Error handling (all pages)

- API errors: inline error banner with message + retry button
- No full-page error states in Phase 1
- Assert `{"detail": str}` message surfaced in the banner
- Network timeout: banner with retry, page does not crash

---

## Accessibility / UX invariants

- All form inputs have associated labels (for screen readers)
- Interactive elements reachable via keyboard (Tab order)
- Status badges convey meaning via text, not colour alone
