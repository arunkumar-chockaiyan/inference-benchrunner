# System Design: InferenceBenchRunner

A visual-first system design for the inference benchmarking platform. Navigate using the diagrams below, then dive into specific sections.

---

## 1. C4 Context Diagram
**Who uses the system and how it connects to external services.**

![C4 Context](./architecture/rendered/c4-context.png)

[Source: `architecture/c4-context.excalidraw`]

**Key actors:**
- **Researcher** — Creates benchmark runs, compares engine performance
- **InferenceBenchRunner** — The system being built
- **Inference Engines** — Ollama, llama.cpp, vLLM, SGLang (local or remote)
- **Observability Stack** — OTel Collector, VictoriaMetrics, Grafana
- **PostgreSQL** — Run configs, prompts, request metadata
- **ClickHouse** — Per-request event rows for analytical drill-down

---

## 2. Component Architecture
**Internal structure: how the backend is organized.**

![Components](./architecture/rendered/component-diagram.png)

[Source: `architecture/component-diagram.excalidraw`]

**Load-bearing abstraction:** `InferenceEngineDriver` ABC ensures adding a new engine requires **zero changes outside its own driver file**.

| Component | Responsibility |
|-----------|-----------------|
| `InferenceEngineDriver` + implementations | Spawn/teardown, health checks, run prompts, list models |
| `execute_run()` | Orchestrate run lifecycle (spawn → healthy → sidecar → execute → cleanup) |
| `OTel Sidecar` (per run) | Scrape metrics, stamp `run_id` label, forward to collector |
| `ollama_shim.py` | Synthetic Prometheus metrics for Ollama (no native `/metrics`) |
| FastAPI Agent | Engine lifecycle control plane for local and remote hosts |
| FastAPI Routes | REST/WebSocket endpoints for CRUD + run control |
| SQLAlchemy Models | Prompts, suites, configs, runs, request records |

---

## 3. Data Flow Diagram
**How data moves through the system during a run.**

![Data Flow](./architecture/rendered/data-flow.png)

[Source: `architecture/data-flow.excalidraw`]

**Storage split (design pattern):**
- **PostgreSQL** — Structured: run configs, prompts, suites, request metadata
- **VictoriaMetrics** — Time-series: metrics stamped with `run_id`, queryable for comparison
- **ClickHouse** — Row-level events (best-effort write from `collect_record()`)

**Flow:**
1. User creates run config → stored in PostgreSQL
2. `execute_run()` spawns engine via agent + starts sidecar after warmup
3. Sidecar scrapes engine's `/metrics` every 5 seconds
4. Each metric gets `run_id`/`model`/`engine`/`host` labels
5. Sidecar buffers → forwards to OTel Collector → VictoriaMetrics
6. Each prompt execution → `RequestRecord` row (latency, tokens, errors) → PostgreSQL + ClickHouse (best-effort)
7. Frontend queries PostgreSQL for metadata, VictoriaMetrics for time-series, ClickHouse for drill-down

---

## 4. Run Execution Lifecycle
**State machine: what happens from "start" to "done".**

![Lifecycle](./architecture/rendered/run-lifecycle.png)

[Source: `architecture/run-lifecycle.excalidraw`]

**States:**
- `PENDING` — Created, waiting to start
- `STARTING` — Engine server being launched via agent
- `WARMING_UP` — Running warmup rounds (cache priming); sidecar not yet started
- `RUNNING` — Warmup done, sidecar up, executing prompt suite with concurrency semaphore
- `COMPLETED` | `FAILED` | `CANCELLED` — Terminal states

**Key invariant:** `run_id` (UUID) is stamped on every artifact:
- OTel metric labels
- `RequestRecord` rows
- Sidecar config
- ClickHouse event rows
- Grafana dashboard variable
- Never reused

**Important timing:** `run_started_at` marks when the sidecar starts (after warmup), not when the engine spawned. Use `run_started_at` for Grafana chart alignment.

---

## 5. Deployment Architecture
**How everything runs together: Docker Compose topology.**

![Deployment](./architecture/rendered/deployment-architecture.png)

[Source: `architecture/deployment-architecture.excalidraw`]

**Services:**
| Service | Port | Purpose |
|---------|------|---------|
| `backend` | 8080 | FastAPI app (uvicorn) |
| `agent` | 8787 | FastAPI engine lifecycle agent |
| `frontend` | 5173 | Vite dev server (or static build) |
| `otel-collector` | 4317 (gRPC) | Receives metrics from sidecars |
| `victoriametrics` | 8428 | Time-series TSDB |
| `grafana` | 3001 | Dashboard + alerts |
| `postgres` | 5432 | OLTP metadata store |
| `clickhouse` | 8123 | Columnar OLAP event store |

**Engine spawning (current architecture):**
- **Universal FastAPI agent** (`agent/agent.py`) runs on every engine host (local or remote)
- Backend calls agent via HTTP (`httpx`) — no SSH
- Local: agent on `localhost:8787`; Remote: agent on Tailscale IP/MagicDNS name `:8787`
- `spawn_mode = "managed"` → agent spawns engine; `"attach"` → engine pre-running (Ollama always attach)
- Authenticated via `X-Agent-Key` shared secret

**Sidecar lifecycle:**
- Per-run Jinja2 template instantiation (on benchmarking host, not engine machine)
- Starts after warmup completes (`run_started_at`)
- Scrapes engine's `/metrics` endpoint
- Forwards to OTel Collector
- Terminates in `finally` block with the run

---

## 6. Metrics Ports by Engine

| Engine | Default Port | Metrics Port | Notes |
|--------|-------------|--------------|-------|
| Ollama | 11434 | 9091 (shim) | No native `/metrics` → Python shim required |
| llama.cpp | 8080 | 8080 | Native Prometheus metrics |
| vLLM | 8000 | 8000 | Native Prometheus metrics |
| SGLang | 30000 | 30000 | Native Prometheus metrics |

---

## 7. API Surface
**Key routes and WebSocket endpoints.**

### Run Management
- `POST /api/runs` — Create and start run (idempotent, returns run_id)
- `GET /api/runs/{id}` — Run status + metadata
- `DELETE /api/runs/{id}` — Cancel in-progress run
- `GET /api/runs/{id}/requests` — Paginated RequestRecord rows (latency, tokens, errors)

### Comparison
- `POST /api/runs/compare` — Compare N run_ids (compute mean/p50/p95, throughput; returns BarChart data)

### Engine Discovery
- `GET /api/engines/{engine}/models` — List models from DB registry for `engine`
- `GET /api/engines` — List supported engines

### Live Progress
- `WS /ws/runs/{id}` — Live stream: `{completed, total, failed, current_tps, elapsed_seconds, eta_seconds, server_alive}` per request

### Prompts & Suites
- `POST /api/prompts`, `GET /api/prompts`, `DELETE /api/prompts/{id}`
- `POST /api/suites`, `GET /api/suites`, `DELETE /api/suites/{id}`

---

## 8. Key Design Decisions

See [`adr/`](../adr/) folder for detailed rationale on:
- ADR-0001: InferenceEngineDriver abstraction (ABC + registry)
- ADR-0002: Storage split (PostgreSQL + VictoriaMetrics + ClickHouse)
- ADR-0003: OTel sidecar per run (benchmarking host, not engine machine)
- ADR-0004: SSH-based remote spawning — **superseded before implementation**
- ADR-0005: Tailscale + FastAPI Agent for remote engine management (current)

---

## 9. Build Phase Order

**Phase 1** (foundation):
1. Database models + SQLAlchemy async setup + Alembic
2. `InferenceEngineDriver` ABC + all four driver implementations (parallel)
3. FastAPI agent (`agent/agent.py`) — spawn/health/status/teardown endpoints
4. `wait_healthy()` utility
5. OTel sidecar template + `start_sidecar()`
6. `execute_run()`, `collect_record()`, `ch_insert()` (services layer)
7. FastAPI routes (CRUD, start, cancel, compare)
8. WebSocket live progress
9. React frontend (run list, new run wizard, detail, compare)
10. Docker Compose + full observability stack (PostgreSQL, ClickHouse, OTel, VictoriaMetrics, Grafana)
11. Grafana dashboard JSON

**Phase 2** (enhancements): Warmup tuning, GPU metrics, exports, saved comparisons, LineChart compare

**Phase 3** (scale): Kafka pipeline (sidecar → Kafka → VictoriaMetrics + ClickHouse consumer); removes `ch_insert()`

---

## 10. Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://bench:bench@localhost:5432/bench

# Observability
OTEL_COLLECTOR_ENDPOINT=http://otel-collector:4317
VICTORIAMETRICS_URL=http://victoriametrics:8428
GRAFANA_URL=http://localhost:3001

# ClickHouse
CLICKHOUSE_URL=http://clickhouse:8123

# Security
SECRET_KEY=<random 32 bytes>
AGENT_SECRET_KEY=<separate random secret for agent auth>

# Agent
AGENT_URL=http://agent:8787

# Phase 3 only
KAFKA_BROKERS=kafka:9092
```

---

## Next Steps

1. **Review diagrams** — Excalidraw sources in `architecture/*.excalidraw`; rendered PNGs in `architecture/rendered/`
2. **Check ADRs** — `docs/adr/` for rationale on all major decisions
3. **Build order** — `docs/spec/11-build-order.md` for current phase and step-by-step progress

---

*Last updated: 2026-04-03*
