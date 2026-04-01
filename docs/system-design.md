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
- **SQLite/PostgreSQL** — Run configs, prompts, request metadata

---

## 2. Component Architecture
**Internal structure: how the backend is organized.**

![Components](./architecture/rendered/component-diagram.png)

[Source: `architecture/component-diagram.excalidraw`]

**Load-bearing abstraction:** `EngineDriver` ABC ensures adding a new engine requires **zero changes outside its own driver file**.

| Component | Responsibility |
|-----------|-----------------|
| `EngineDriver` + implementations | Spawn/teardown, health checks, run prompts, list models |
| `execute_run()` | Orchestrate run lifecycle (spawn → healthy → sidecar → execute → cleanup) |
| `OTel Sidecar` (per run) | Scrape metrics, stamp `run_id` label, forward to collector |
| `ollama_shim.py` | Synthetic Prometheus metrics for Ollama (no native `/metrics`) |
| FastAPI Routes | REST/WebSocket endpoints for CRUD + run control |
| SQLAlchemy Models | Prompts, suites, configs, runs, request records |

---

## 3. Data Flow Diagram
**How data moves through the system during a run.**

![Data Flow](./architecture/rendered/data-flow.png)

[Source: `architecture/data-flow.excalidraw`]

**Storage split (design pattern):**
- **SQLite** — Structured: run configs, prompts, suites, request metadata
- **VictoriaMetrics** — Time-series: metrics stamped with `run_id`, queryable for comparison
- **ClickHouse** (Phase 3 only) — Row-level events, added only when needed

**Flow:**
1. User creates run config → stored in SQLite
2. `execute_run()` spawns engine + sidecar
3. Sidecar scrapes engine's `/metrics` every N seconds
4. Each metric gets `run_id`/`model`/`engine` labels
5. Sidecar buffers → forwards to OTel Collector → VictoriaMetrics
6. Each prompt execution → `RequestRecord` row (latency, tokens, errors)
7. Frontend queries SQLite for metadata, VictoriaMetrics for time-series, computes stats

---

## 4. Run Execution Lifecycle
**State machine: what happens from "start" to "done".**

![Lifecycle](./architecture/rendered/run-lifecycle.png)

[Source: `architecture/run-lifecycle.excalidraw`]

**States:**
- `PENDING` — Created, waiting to start
- `SPAWNING` — Engine server being launched
- `WAITING_HEALTHY` — Engine online, waiting for readiness signal
- `WARMUP` — Running warmup rounds (cache priming)
- `RUNNING` — Executing prompt suite with concurrency semaphore
- `CLEANUP` — Tearing down engine/sidecar (always, even on failure)
- `COMPLETED` | `FAILED` | `CANCELLED` — Terminal states

**Key invariant:** `run_id` (UUID) is stamped on every artifact:
- OTel metric labels
- `RequestRecord` rows
- Sidecar config
- Grafana dashboard variable
- Never reused

---

## 5. Deployment Architecture
**How everything runs together: Docker Compose topology.**

![Deployment](./architecture/rendered/deployment-architecture.png)

[Source: `architecture/deployment-architecture.excalidraw`]

**Services:**
| Service | Port | Purpose |
|---------|------|---------|
| `backend` | 8080 | FastAPI app (uvicorn) |
| `frontend` | 5173 | Vite dev server (or static build) |
| `otel-collector` | 4317 (gRPC) | Receives metrics from sidecars |
| `victoriametrics` | 8428 | Time-series TSDB |
| `grafana` | 3000 | Dashboard + alerts |
| `sqlite` | — | `data/bench.db` (local file) |

**Engine spawning (v1 architecture):**
- Local engines: spawn directly via subprocess
- Remote engines: SSH-based via `asyncssh` (works on any machine with SSH, no pre-installed software)

**Sidecar lifecycle:**
- Per-run Jinja2 template instantiation
- Scrapes engine's `/metrics` endpoint
- Forwards to OTel Collector
- Dies with run cleanup

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
- `POST /api/runs/compare` — Compare N run_ids (compute mean/p50/p95/p99, throughput, cost, model switching latency)

### Engine Discovery
- `GET /api/engines/{engine}/models` — List available models for `engine` + `host`
- `GET /api/engines` — List supported engines

### Live Progress
- `WS /ws/runs/{id}` — Live stream: `{event: "request_done", latency_ms, tokens, ...}` per request

### Prompts & Suites
- `POST /api/prompts`, `GET /api/prompts`, `DELETE /api/prompts/{id}`
- `POST /api/suites`, `GET /api/suites`, `DELETE /api/suites/{id}`

---

## 8. Key Design Decisions

See [`adr/`](../adr/) folder for detailed rationale on:
- ADR-0001: EngineDriver abstraction
- ADR-0002: Storage split (SQLite + VictoriaMetrics)
- ADR-0003: OTel sidecar per run (not centralized)
- ADR-0004: SSH-based remote spawning (v1 architecture)
- ADR-0005: Concurrency via semaphore (not process pools)

---

## 9. Build Phase Order

**Phase 1** (foundation):
1. Database models + SQLAlchemy setup
2. `EngineDriver` base class + all four implementations
3. `wait_until_healthy` utility
4. OTel sidecar template + `start_sidecar()`
5. `execute_run()` orchestrator
6. FastAPI routes (CRUD, start, cancel, compare)
7. WebSocket live progress
8. React frontend (run list, new run wizard, detail, compare)
9. Docker Compose + monitoring stack
10. Grafana dashboard JSON

**Phase 2** (enhancements): Warmup tuning, auto-retry, GPU metrics, exports, saved comparisons

**Phase 3** (advanced): Kafka, ClickHouse (add only when SQL drill-down is needed)

---

## 10. Environment Variables

```bash
# Database
DATABASE_URL=sqlite:///./data/bench.db

# Observability
OTEL_COLLECTOR_ENDPOINT=http://otel-collector:4317
VICTORIAMETRICS_URL=http://victoriametrics:8428
GRAFANA_URL=http://grafana:3000

# Security
SECRET_KEY=<random 32 bytes>

# Remote SSH (optional)
SSH_DEFAULT_USER=ubuntu
SSH_KEY_PATH=~/.ssh/id_rsa

# Phase 3 only
KAFKA_BROKERS=kafka:9092
CLICKHOUSE_URL=http://clickhouse:8123
```

---

## Next Steps

1. **Review diagrams** — Do they match your mental model?
2. **Check ADRs** — Rationale behind key decisions
3. **Refine gaps** — Which areas need more detail before Phase 1 starts?
4. **Iterate** — Diagrams live in `architecture/*.excalidraw` — edit and re-export as needed

---

*Generated from `inference_bench_spec.md`. Last updated: 2026-03-31*
