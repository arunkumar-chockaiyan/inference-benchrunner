# QA Spec — End-to-End Scenarios

Source: all spec files. Requires real services (see prerequisites).

---

## Prerequisites

| Service | Requirement |
|---------|------------|
| PostgreSQL | Running; migrations applied (`alembic upgrade head`) |
| Ollama | Running at `localhost:11434`; `tinyllama` model pulled |
| OTel Collector | Running (Docker); accepting OTLP on `4317` |
| VictoriaMetrics | Running (Docker); receiving from OTel Collector |
| `otelcol-contrib` | Installed binary (for sidecar) |
| Backend | `uvicorn main:app --port 8080` |
| Agent | `uvicorn agent:app --port 8787` |

Environment: `.env` with `DATABASE_URL`, `OTEL_COLLECTOR_ENDPOINT`, `AGENT_SECRET_KEY`.

Mark E2E tests with `@pytest.mark.e2e` and gate with `--run-e2e` flag in CI.

---

## Scenario 1 — Ollama local run (happy path)

The most critical scenario: validates the full benchmark lifecycle.

### Steps

1. Create a prompt suite with 3 prompts (via `POST /api/prompts` + `POST /api/suites`)
2. Create and start a run (via `POST /api/runs`) with:
   - `engine="ollama"`, `model="tinyllama"`, `host="localhost"`, `port=11434`
   - `spawn_mode="attach"`, `warmup_rounds=1`, `concurrency=1`, `auto_retry=0`
3. Connect WebSocket to `WS /ws/runs/{id}`
4. Poll until status = `"completed"` (timeout: 120s)
5. Fetch `GET /api/runs/{id}/requests`

### Assertions

| Assertion | Details |
|-----------|---------|
| Status progresses | `pending → starting → warming_up → running → completed` |
| `run_started_at` set | After warmup; not null |
| `warmup_duration_ms` set | Positive float |
| `completed_requests = 3` | One record per prompt |
| `failed_requests = 0` | All succeed |
| All `RequestRecord.run_id` = `run.id` | run_id stamped on every record |
| `ttft_ms` populated | Non-null for all records |
| `total_latency_ms > ttft_ms` | Latency includes all tokens |
| `tokens_per_second` positive | Engine TPS reported |
| OTel metrics in VictoriaMetrics | Query `bench_request_ttft_ms{run_id="..."}` → non-empty |
| `bench_run_start_timestamp` present | One data point, value = Unix ts of `run_started_at` |
| Sidecar config file cleaned up | `/tmp/otel-sidecar-{run_id}.yaml` does not exist after run |
| Sidecar buffer dir cleaned up | `/tmp/otel-buffer/{run_id}` empty or removed |

---

## Scenario 2 — Run cancellation

1. Create a suite with 20 prompts (enough to take >5 seconds)
2. Start run with Ollama
3. Wait until `status = "running"` via WebSocket
4. Call `DELETE /api/runs/{id}`
5. Assert WebSocket terminal event: `status = "cancelled"`, code 1000

### Assertions

- `Run.status = "cancelled"` in DB
- `completed_requests + failed_requests < 20` (stopped mid-run)
- Ollama shim process is terminated (check `/proc` or mock subprocess)
- Sidecar process is terminated
- OTel sidecar config file deleted

---

## Scenario 3 — render_prompt() variable substitution (integration)

1. Create prompt: `content="Summarize: {{topic}}"`, `variables={"topic": "default"}`
2. Create run with `variable_overrides={"topic": "quantum computing"}`
3. Run benchmark (1 prompt, 1 warmup round)
4. Assert `RequestRecord` was created (engine received the prompt)
5. No assertion on response content — just that the prompt was dispatched

---

## Scenario 4 — Retry on transient failure

Requires a mock engine that fails the first request then succeeds.
Use `respx` to mock the engine HTTP layer.

1. Configure `auto_retry=2`
2. First call to engine → `httpx.TimeoutException`
3. Second call → success
4. Assert `RequestRecord.attempt = 2`
5. Assert `Run.failed_requests = 0` (success after retry)
6. Assert linear backoff: `asyncio.sleep` called with `1 * 1 = 1` second

---

## Scenario 5 — Engine watchdog triggers

Requires mock engine.

1. Mock `is_healthy()`: returns `True` for 2 polls, then `False`
2. Start run with `watchdog_interval_s=1` (fast poll for test)
3. Assert run transitions to `"failed"` with `error_message` containing "unhealthy"
4. Assert cleanup runs: sidecar terminated, engine teardown called (if owned)

---

## Scenario 6 — Backend restart mid-run (`recover_stale_runs`)

1. Start a run (Ollama attach mode); confirm `status = "running"` in DB
2. Simulate backend crash: manually set `Run.status = "running"` in DB with stale timestamp
3. Restart backend
4. `recover_stale_runs()` runs on startup
5. Assert run transitions to `"failed"` with error: "Run was in-progress when backend restarted"
6. For attach mode: no agent DELETE call (agent not involved)
7. `cleanup_warning` set if agent unreachable during recovery

---

## Scenario 7 — ClickHouse best-effort write failure

1. Configure ClickHouse connection to point to a non-running port
2. Run benchmark with 3 prompts
3. Assert run completes successfully (`status = "completed"`)
4. Assert all 3 `RequestRecord` rows exist in PostgreSQL
5. Assert warning log entries contain "ClickHouse insert failed"

---

## Scenario 8 — Model registry sync and staleness

1. Mock Ollama `GET /api/tags` to return `["modelA", "modelB"]`
2. Call `POST /api/engines/ollama/models/sync?host=localhost&port=11434`
3. Assert `modelA` and `modelB` in DB with `source="synced"`, `is_stale=False`
4. Add manual model `modelC` (`source="manual"`)
5. Mock Ollama to return only `["modelA"]` (modelB disappears)
6. Sync again
7. Assert `modelB.is_stale = True` (not deleted)
8. Assert `modelC` unchanged (`source="manual"`, `is_stale=False`)
9. Assert `modelA.last_synced` updated

---

## Scenario 9 — Saved comparison shareable URL

1. Complete two runs (run A, run B)
2. `POST /api/runs/compare` with both run IDs, `metric="p99"`
3. Assert response has `avg`, `p99`, `min`, `max`, `stddev`, `sample_count` for each run
4. `POST /api/comparisons` to save
5. Assert response includes `token` (non-empty URL-safe string)
6. `GET /api/comparisons/{token}` → `200` with same run data
7. `GET /api/comparisons/invalid-token` → `404`

---

## Scenario 10 — Parallel concurrency (semaphore)

Requires mock engine with controllable response delay.

1. Suite: 6 prompts; `concurrency=2`
2. Mock engine: each response takes 500ms
3. Run benchmark; time total execution
4. Assert total time ≈ 3 × 500ms (6 prompts / 2 concurrent = 3 batches)
5. Assert never more than 2 simultaneous in-flight requests (semaphore enforced)

---

## CI test matrix

| Scenario | Type | Required services | Runtime |
|----------|------|-------------------|---------|
| 1 — Ollama happy path | E2E | All | ~60s |
| 2 — Cancellation | E2E | Ollama + backend | ~15s |
| 3 — Variable substitution | Integration | PostgreSQL + mock engine | ~5s |
| 4 — Retry | Integration | Mock engine | ~5s |
| 5 — Watchdog | Integration | Mock engine | ~5s |
| 6 — Restart recovery | Integration | PostgreSQL | ~5s |
| 7 — ClickHouse failure | Integration | PostgreSQL | ~10s |
| 8 — Model sync | Integration | PostgreSQL + mock engine | ~5s |
| 9 — Saved comparison | API | PostgreSQL | ~5s |
| 10 — Concurrency | Integration | Mock engine | ~10s |

**CI gates:**
- Unit tests: always run (no external services)
- Integration tests: run on every PR (PostgreSQL in Docker, engines mocked)
- E2E scenarios 1–2: run nightly or on release branch (full Ollama stack)
