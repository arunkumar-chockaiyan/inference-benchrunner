# InferenceBenchRunner — QA Test Specification Overview

## Purpose

This document describes the quality assurance strategy for InferenceBenchRunner:
a benchmarking tool that fires prompt suites at LLM inference engines, collects
per-request metrics via an OTel sidecar, stores results in VictoriaMetrics and
ClickHouse, and compares runs in Grafana.

## Document index

| File | Scope |
|------|-------|
| `00-qa-overview.md` | This file — strategy, priorities, test pyramid |
| `01-data-models.md` | PostgreSQL models, SQLAlchemy async, Alembic migrations |
| `02-engine-drivers.md` | All four drivers + ABC contract |
| `03-run-execution.md` | execute_run(), collect_record(), render_prompt(), watchdog |
| `04-otel-sidecar.md` | Sidecar lifecycle, template rendering, metric labels |
| `05-agent-remote.md` | Agent endpoints, spawn_mode, Tailscale, auth |
| `06-api-routes.md` | FastAPI routes, WebSocket, error shapes, pagination |
| `07-frontend.md` | React pages, wizard flow, WebSocket live updates |
| `08-metrics-storage.md` | VictoriaMetrics labels, ClickHouse best-effort writes |
| `09-e2e-scenarios.md` | Full run lifecycle scenarios across all engines |

---

## Test pyramid

```
           ┌───────────────────────────────┐
           │        E2E / Integration       │  ← 09-e2e-scenarios.md
           │   (real engines + full stack)  │
           ├───────────────────────────────┤
           │    API / Contract Tests         │  ← 06-api-routes.md
           │  (FastAPI TestClient / httpx)  │
           ├───────────────────────────────┤
           │       Unit Tests               │  ← 01-08 specs
           │ (drivers, runner, sidecar,     │
           │  models — isolated w/ mocks)   │
           └───────────────────────────────┘
```

Ratio target: **60% unit / 30% API contract / 10% E2E**

---

## Quality dimensions

### 1. Correctness

The system makes precise measurement claims. These must be exact:

| Invariant | Risk if broken |
|-----------|---------------|
| `run_id` stamped on every OTel metric | Grafana shows mixed-run data |
| `run_started_at` = sidecar start time | Charts misalign across runs |
| Warmup requests excluded from metrics | Inflated TTFT in benchmarks |
| `ResponseMeta` carries exact token counts | Wrong TPS and token metrics |
| `render_prompt()` applies overrides on top of defaults | Wrong prompts sent |

### 2. Reliability

The benchmark runner must survive transient failures without losing data:

- Retry logic (`auto_retry`) covers transient httpx errors
- `recover_stale_runs()` handles backend restart mid-run
- Sidecar disk buffer covers central collector outages up to 5 minutes
- ClickHouse write failures are best-effort — must not fail the run
- Cleanup order in `finally` must always execute (shim → sidecar → teardown)

### 3. Safety / Isolation

| Rule | Consequence of violation |
|------|--------------------------|
| `teardown()` is no-op when `owned=False` | Kill a shared inference server |
| Ollama always `attach` mode | Agent wrongly kills system Ollama service |
| `run_id` is immutable after creation | Corrupted metric attribution |
| Agent key validation on all non-health routes | Unauthorized engine control |
| `stream_prompt()` never routed through agent | Latency added to measured data |

### 4. Performance

- WebSocket events emitted every 2 seconds — no blocking DB queries on hot path
- `asyncio.Semaphore(config.concurrency)` must bound parallel requests
- `asyncio.create_subprocess_exec` for sidecar (non-blocking, no PIPE buffers)
- All SQLAlchemy operations async — no sync session leaks

---

## Test environment requirements

### Unit tests
- PostgreSQL test database (Docker or `pytest-postgresql`)
- No real inference engines required — all drivers mocked via `httpx.MockTransport`
- `otelcol-contrib` binary not required — `start_sidecar()` tested with subprocess mock
- Environment: `.env.test` with `DATABASE_URL`, `OTEL_COLLECTOR_ENDPOINT`, `AGENT_SECRET_KEY`

### API contract tests
- FastAPI `TestClient` (sync) or `httpx.AsyncClient` with `ASGITransport`
- PostgreSQL test DB with Alembic migrations applied
- Agent endpoints mocked via `respx` or a local stub FastAPI app

### E2E tests
- Real Ollama instance (localhost:11434) — CI can pull a small model (e.g. `tinyllama`)
- `otelcol-contrib` installed
- VictoriaMetrics running (Docker)
- Central OTel Collector running (Docker)
- Full `docker compose up` or partial stack via `pytest` fixtures

---

## Critical path — test priority order

These areas carry the highest risk and should be tested first:

1. **run_id propagation** — unit + integration (sidecar template, OTel labels, DB records)
2. **execute_run() lifecycle** — status transitions, cleanup on failure/cancel
3. **collect_record() metrics** — TTFT, latency, token count accuracy
4. **Driver spawn/teardown contracts** — managed vs attach, owned flag
5. **Agent authentication** — key validation, 401 on missing/wrong key
6. **validate_config()** — blocks bad configs before any process is spawned
7. **recover_stale_runs()** — backend restart safety
8. **WebSocket** — live progress, terminal state closure, reconnect on unexpected close

---

## Toolchain

| Tool | Purpose |
|------|---------|
| `pytest` + `pytest-asyncio` | Async test runner |
| `httpx` + `respx` | Mock HTTP for driver and agent calls |
| `pytest-postgresql` or Docker fixture | PostgreSQL for model tests |
| `Alembic` | Apply migrations before each test session |
| FastAPI `TestClient` | API route tests |
| `factory_boy` or plain fixtures | Model factories for DB setup |
| `pytest-cov` | Coverage gate (target: 80% backend) |

---

## Coverage gates

| Layer | Target |
|-------|--------|
| `backend/runner.py` | 90% |
| `backend/drivers/*.py` | 85% |
| `backend/routers/*.py` | 80% |
| `backend/sidecar.py` | 80% |
| `backend/agent.py` | 80% |
| Overall backend | 80% |

---

## What is NOT tested here

- Grafana dashboard JSON (visual — manual review)
- Tailscale ACL rules (infrastructure — operational checklist)
- docker-compose service ordering (smoke-tested in E2E, not unit)
- Phase 3 (Kafka, ClickHouse fanout) — out of scope until Phase 3 triggers

---

## Naming conventions

```
backend/tests/
  test_models.py              ← 01-data-models
  drivers/
    test_base.py              ← ABC contract tests
    test_ollama.py
    test_llamacpp.py
    test_vllm.py
    test_sglang.py
  test_runner.py              ← execute_run, collect_record, render_prompt
  test_sidecar.py             ← start_sidecar, template rendering
  test_agent.py               ← agent endpoints
  routers/
    test_runs.py
    test_prompts.py
    test_engines.py
    test_comparisons.py
  test_e2e.py                 ← full lifecycle (requires real Ollama)
```

All test files mirror the source tree. Tests are async where the source is async.
Use `@pytest.mark.asyncio` or `asyncio_mode = "auto"` in `pytest.ini`.
