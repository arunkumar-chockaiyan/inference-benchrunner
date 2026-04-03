# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project status

Specification complete. No source code written yet.
Build according to docs/spec/11-build-order.md — Phase 1 first.
Check off steps in 11-build-order.md as they complete.
Note any deviations from spec in companion NOTES.md files (e.g. 02-engine-drivers.NOTES.md).

## What this is

A benchmarking tool for LLM inference engines. Users configure runs (engine +
model + prompt suite + parameters), fire them at local or remote inference
servers, collect per-request metrics via an OTel sidecar, and compare results
across runs in Grafana.

**Supported engines:** Ollama, llama.cpp server, vLLM, SGLang

---

## Specification files

Always read before starting any task:
- docs/spec/00-overview.md       — project context, stack, design decisions, do-nots
- docs/spec/11-build-order.md    — current phase, what's been built, what's next

Read when relevant to your task:
- docs/spec/01-data-models.md    — any work touching models, DB, or schemas
- docs/spec/02-engine-drivers.md — any work in backend/drivers/
- docs/spec/03-run-execution.md  — execute_run(), collect_record(), run lifecycle
- docs/spec/04-otel-sidecar.md   — OTel sidecar, metrics collection
- docs/spec/05-remote-support.md — Tailscale, agent, remote spawning
- docs/spec/06-api-routes.md     — FastAPI routes, request/response shapes
- docs/spec/07-frontend.md       — React pages, components, UI behaviour
- docs/spec/08-metrics-storage.md — VictoriaMetrics, what gets stored where
- docs/spec/09-grafana.md        — Grafana dashboard, panels, provisioning
- docs/spec/10-infrastructure.md — docker-compose, OTel collector config
- docs/spec/12-phase3.md         — Kafka pipeline (read ONLY when triggered)
- docs/spec/15-environment.md    — all env vars + .env.example

Do NOT read 12-phase3.md unless explicitly instructed.

---

## Stack

**Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, httpx, opentelemetry-sdk
**Frontend:** React 18 + TypeScript, Vite, Zustand, Tailwind CSS, Recharts
**Infra:** VictoriaMetrics, OTel Collector (otelcol-contrib), Grafana, Docker Compose
**Network:** Tailscale for remote machine connectivity — no SSH
**Removed:** asyncssh — not used anywhere

---

## Project layout

```
backend/
  drivers/
    __init__.py       # DRIVERS registry + get_driver()
    base.py           # InferenceEngineDriver ABC + dataclasses
    ollama.py         # OllamaDriver (attach-only)
    llamacpp.py       # LlamaCppDriver
    vllm.py           # VllmDriver
    sglang.py         # SGLangDriver
    ollama_shim.py    # Prometheus shim for Ollama metrics
  services/
    runner.py         # execute_run(), render_prompt()
    collector.py      # collect_record()
    clickhouse.py     # ch_insert() — best-effort ClickHouse write
    sidecar.py        # start_sidecar()
  schemas/
    run.py            # RunCreate, RunRead, RunSummary
    prompt.py         # PromptCreate, PromptRead
    suite.py          # SuiteCreate, SuiteRead
    engine.py         # EngineModelRead
    comparison.py     # ComparisonRequest, ComparisonResult
  routers/            # FastAPI route modules
  tests/              # mirrors source tree
  main.py             # FastAPI backend entrypoint
  database.py         # SQLAlchemy async setup
  models.py           # All SQLAlchemy models
  config.py           # pydantic-settings BaseSettings
agent/
  agent.py            # FastAPI agent — manages engine lifecycle
  requirements.txt    # minimal: fastapi, uvicorn, httpx only
  Dockerfile          # separate image — no backend deps
  tests/              # agent tests
frontend/
  src/
    pages/
      RunList.tsx       # run list page
      NewRunWizard.tsx  # 4-step wizard
      RunDetail.tsx     # run detail + live progress
      Compare.tsx       # comparison page (BarChart)
    components/         # shared UI components
    store/              # Zustand state
    api/                # typed API client
infra/
  sidecar.yaml.j2     # Jinja2 OTel sidecar config template
  otel-collector.yaml # Central OTel Collector config
  clickhouse/
    init.sql          # inference_requests schema (auto-run on container start)
  grafana/
    provisioning/
      datasources/victoriametrics.yaml
      datasources/clickhouse.yaml
      dashboards/dashboard.yaml
      dashboards/bench.json           # UID fixed: "bench-dashboard"
data/                 # gitignored
docs/
  spec/               # all spec files live here
docker-compose.yml
docker-compose.override.yml  # dev hot-reload (auto-merged)
Makefile              # common dev commands
.env.example
```

---

## Running the stack

```bash
# Full stack
docker compose up

# Backend dev server
cd backend && uvicorn main:app --reload --port 8080

# Agent dev server
cd agent && uvicorn agent:app --reload --port 8787

# Frontend dev server
cd frontend && npm run dev

# Backend tests
cd backend && pytest -x -v --tb=short --no-header

# Frontend tests
cd frontend && npm test -- --run

# Database migrations
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "description"
```

---

## Code conventions

- All backend code is async-first — use `async def` and `await` everywhere
- SQLAlchemy sessions via `async with AsyncSession` — never use sync sessions
- Errors: raise typed `HTTPException` at the route layer; drivers raise plain `RuntimeError`
- One file per EngineDriver — ollama.py, llamacpp.py, vllm.py, sglang.py
- Tests live in `backend/tests/` mirroring the source tree; prefix with `test_`
- Never import from `frontend/` in `backend/` or vice versa
- Use Alembic for all schema changes — never modify DB schema directly

---

## Parallelism strategy

When given a multi-part task, identify independent subtasks and run them
concurrently using background subagents. Always state what you are running
in parallel before starting. Ask before parallelizing if tasks share files
or have unclear dependencies.

Example: implementing the four drivers (steps 3a–3d) should always run in
parallel — one subagent per driver file.

---

## Do not

- Do NOT add Kafka or Phase 3 infrastructure until explicitly instructed
- ClickHouse IS part of Phase 1 — use clickhouse-connect; ch_insert() lives in services/clickhouse.py
- Do NOT modify InferenceEngineDriver ABC when adding a new engine — new engines go in their own driver file only
- Do NOT reuse or mutate run_id — set once at run creation, immutable
- Do NOT skip the run_id label when writing OTel metrics — every metric must carry it
- Do NOT use synchronous SQLAlchemy — async throughout
- Do NOT use asyncssh — remote access is via httpx agent over Tailscale
- Do NOT add dependencies not in the spec without asking first
- Do NOT read docs/spec/12-phase3.md unless explicitly instructed
- Do NOT route stream_prompt() or list_models() through the agent — data plane is always direct to engine
- Do NOT call list_models() from the wizard — wizard reads from EngineModel DB registry

---

## Key architectural rules

**run_id is the spine.** Set at run creation. Stamped on every OTel metric,
every RequestRecord, used as Grafana dashboard variable. Never reused.

**Universal agent for control plane.** The FastAPI agent (agent/agent.py)
manages engine lifecycle for ALL runs — local and remote. Location is just
config.host. spawn_mode has two values only: "managed" (agent spawns engine)
or "attach" (engine already running). Ollama is ALWAYS attach mode.

**Data plane is always direct.** stream_prompt() and list_models() call the
engine directly — never routed through the agent. Agent is control plane only.

**Sidecar starts after warmup.** Warmup requests are discarded. run_started_at
marks sidecar start — use this for Grafana chart alignment, not started_at.

**execute_run() owns RequestRecord construction.** Drivers stream tokens via
stream_prompt() → AsyncIterator[str | ResponseMeta]. collect_record() consumes
the stream and builds the RequestRecord. Drivers do not build records.

**EngineModel registry decouples planning from runtime.** Model data lives in
PostgreSQL. list_models() is only called during explicit sync. Wizard reads from DB.
validate_config() checks DB registry — no live engine call needed.

**SpawnResult owns cleanup contract.** teardown() is a no-op when
SpawnResult.owned=False. Never kill a server we didn't start.

**Tailscale for remote access.** Remote hosts should be Tailscale IPs (100.x.x.x)
or MagicDNS names (*.ts.net). No SSH, no asyncssh.

---

## Session memory

After completing any phase step or making a significant deviation from the spec,
update docs/spec/11-build-order.md (tick the step) and create or update the
relevant NOTES.md companion file:

```
docs/spec/02-engine-drivers.NOTES.md   ← deviations in driver implementations
docs/spec/01-data-models.NOTES.md      ← schema changes from spec
docs/spec/03-run-execution.NOTES.md    ← changes to execute_run() or collect_record()
```

Format:
```markdown
## Step N — <what was built> — <date>
- Deviation: <what changed from spec and why>
- Next session needs to know: <anything that affects subsequent steps>
```