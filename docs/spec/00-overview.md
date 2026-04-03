# Inference Benchrunner — Overview, Stack & Design Decisions

## 1. Project overview

### Purpose
Users configure a run (engine + model + prompt suite + parameters), fire it at
a local or remote inference server, collect per-request metrics via an OTel
sidecar, store results in VictoriaMetrics, and compare runs in Grafana with
aligned time-axis charts and confidence bands.

### Primary users
Small teams (2–10 people) evaluating inference engines and models. All users
share the same instance. No per-user access control in v1. SECRET_KEY reserved
for future auth middleware — not used in Phase 1.

### Supported inference engines
- Ollama (local, port 11434)
- llama.cpp server mode / llama-server (local or remote, port 8080)
- vLLM (local or remote, port 8000, OpenAI-compatible API)
- SGLang (local or remote, port 30000, OpenAI-compatible API)

### Deployment targets
- Local machine (same host as app backend)
- Remote servers / cloud VMs via lightweight agent over Tailscale

---

## 2. Technology stack

### Backend
- Language: Python 3.13+
- Framework: FastAPI
- Process management: subprocess (local), httpx agent calls (remote via Tailscale)
- OTel SDK: opentelemetry-sdk, opentelemetry-exporter-otlp
- HTTP client: httpx (async) — used for engine calls AND remote agent calls
- Database migrations: Alembic (from day 1 — makes SQLite→PostgreSQL a config change)
- Task queue: asyncio background tasks (v1); Celery optional for v2
- Metrics shim: prometheus-client — used by ollama_shim.py to expose synthetic Prometheus /metrics on port 9091

### Frontend
- Framework: React 19 + TypeScript
- Charts: Recharts (chosen over Chart.js — JSX-native, easier Tailwind integration)
- State: Zustand
- Styling: Tailwind CSS v4 (Rust engine, CSS-native @theme config — no tailwind.config.js)
- Build: Vite v8 (Rolldown/Rust bundler; dev server for Phase 1; nginx container added in Phase 2)

### Infrastructure (self-hosted)
- Metrics store: VictoriaMetrics (single-node for v1)
- Telemetry collector: OpenTelemetry Collector (otelcol-contrib)
- Dashboards: Grafana
- Network: Tailscale for remote machine connectivity (no SSH required)
- Optional (phase 3): Apache Kafka, ClickHouse

### Data persistence
- App database: PostgreSQL 17 (asyncpg driver; SQLite dropped per Phase 1 decision)
- ORM: SQLAlchemy 2.0 (async)

### Removed dependencies
- asyncssh — removed. Remote spawning handled by lightweight agent over Tailscale.

---

## Do not

- Do NOT add Kafka or Phase 3 infrastructure until explicitly instructed
- ClickHouse IS part of Phase 1 — ch_insert() in services/clickhouse.py, best-effort write from collect_record()
- Do NOT modify InferenceEngineDriver ABC when adding a new engine — new engines go in their own driver file only
- Do NOT reuse or mutate run_id — set once at run creation, immutable
- Do NOT skip the run_id label when writing OTel metrics — every metric must carry it
- Do NOT use synchronous SQLAlchemy — async throughout
- Do NOT add dependencies not in the spec without asking first
- Do NOT read 12-phase3.md unless explicitly instructed

---

## 16. Key design decisions and rationale

**run_id is the spine of the whole system.** Set at run creation. Injected into
the OTel sidecar, stamped on every metric, stored in every RequestRecord, used
as the Grafana dashboard variable. Never reused.

**Grafana charts align to run_started_at, not started_at.** run_started_at marks
the moment warmup completed and the sidecar started. Aligning charts here ensures
only benchmark data appears, and runs started at different wall-clock times are
still comparable on a relative time axis (seconds since benchmark began).

**OTel sidecar starts after warmup.** Warmup primes the engine's KV cache and
GPU memory. Starting the sidecar after warmup ensures Grafana shows only
steady-state performance data. Warmup duration logged to SQLite for UI visibility.

**execute_run() owns RequestRecord construction.** Drivers stream raw tokens via
stream_prompt(). collect_record() consumes the stream, measures TTFT and latency,
and builds the RequestRecord. Drivers handle streaming; orchestrator handles
measurement.

**ResponseMeta carries exact token counts from the engine.** All four engines
report exact token counts in their final stream chunk. tokens_per_second uses
engine-reported TPS for Ollama and llama.cpp; falls back to wall-clock TPS for
vLLM and SGLang. TPS is not directly comparable across engine families — noted
in the UI with a source indicator.

**SpawnResult replaces int pid.** A plain integer cannot distinguish "remote PID
we own" from "no PID because we attached." SpawnResult carries owned, local_pid,
remote_pid, host, and agent_port — everything teardown() needs to act correctly.
teardown() is a no-op when owned=False.

**Tailscale replaces SSH for remote access.** asyncssh removed. Remote machines
reachable directly over the Tailnet. spawn_mode="attach" (default for remote
hosts) requires no process control. spawn_mode="agent" uses a lightweight
FastAPI agent called via httpx.

**spawn_mode gives users explicit control over server lifecycle. managed (agent spawns
and manages engine, local or remote), attach (connect to existing engine, any host, always
no teardown). Prevents accidental double-spawning and
accidental teardown of shared servers.

**InferenceEngineDriver abstraction is load-bearing.** All orchestration goes
through the ABC. Adding a new engine requires zero changes outside its own
driver file. get_metrics_port() on the driver (not a hardcoded dict) enforces this.

**asyncio background tasks before Celery.** Sufficient for Phase 1 concurrency.
Add Celery only if runs need to survive backend restarts or distributed workers
are needed.

**PostgreSQL from day 1.** Adopted from Phase 1 — asyncpg driver, native UUID/JSONB/timestamptz types throughout. Phase 2 Step 22 (migration) is N/A.

**VictoriaMetrics before ClickHouse.** Covers 90% of use cases with minimal
operational overhead. Add ClickHouse only when row-level SQL drill-down is needed.

**Recharts over Chart.js.** JSX-native, easier Tailwind integration, consistent
with React component model.

**Chart time axis aligned to run_started_at (relative seconds).** Runs started
at different wall-clock times are still comparable on the compare page.

**EngineModel registry decouples planning from runtime.** Model data lives in
SQLite, not fetched live from engines. Users browse, plan, and create runs
without the engine running. list_models() is only called during explicit sync.
Manual entries (source="manual") are never overwritten by sync — user owns them.
llamacpp models are always manual (no discovery API). Enables run scheduling
without any additional data model changes.
