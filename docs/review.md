# Architecture & Design Review

Scope: overall architecture and design correctness only — not implementation detail.
Source: spec review against `02-engine-drivers.md` prior to Phase 1 build start.

---

## Open Items

### R-08 — Tailscale ACL incomplete — engine ports missing
**File:** `docs/spec/05-remote-support.md`
**Issue:** The ACL section stated only `bench-host → remote-machine:8787` (agent port). Engine ports (8000, 8080, 30000) were described as "internal to the remote machine." But `stream_prompt()` and `list_models()` call the engine directly from the benchmarking host, and the OTel sidecar scrapes `/metrics` from the benchmarking host too. Without engine port access the data plane and sidecar scraping both fail for every remote run.
**Fix:** Updated ACL section to include all required port groups (8787, 8080, 8000, 30000) with explanations for why each is needed. Clarified Ollama is always local — no remote port needed.

---

### R-09 — `TAILSCALE_ENABLED` env var silently disables Tailscale address warning
**File:** `docs/spec/05-remote-support.md`
**Issue:** `validate_config()` gated the Tailscale address warning behind `os.environ.get("TAILSCALE_ENABLED")`. If the var is unset (likely in most setups), the warning never fires — users could silently configure a non-Tailscale remote address with no feedback.
**Fix:** Removed the env var gate. Warning now fires unconditionally whenever `config.host` is not localhost/127.0.0.1. Also added "Remote access without Tailscale is unsupported" to the warning text.

---

### S-08 — Suite version history not captured — post-run edits untracked (Phase 3)
**File:** `docs/spec/01-data-models.md`
**Issue:** `PromptSuite.version` is an auto-incrementing counter but old suite contents are overwritten on every save. There is no way to answer "which prompts were in the suite at version N?" or "did the suite change between Run A and Run B?". `Run.config_snapshot` stores the `RunConfig` (including `suite_id`) but not the suite prompt list. Reconstruction from `RequestRecord.prompt_id` is possible but loses prompt order and breaks if prompts are later edited or deleted.
**Status:** Deferred to Phase 3.
**Phase 1 behaviour:** `PromptSuite.version` acts as an optimistic concurrency guard only — UI can warn "suite was edited since this run". Prompt history reconstructed from `RequestRecord.prompt_id` per run.
**Phase 3 action:** Add `SuiteSnapshot` table — immutable ordered prompt list captured at run start, linked to `Run`. Enables exact replay and diff between runs.

---

### S-09 — agent.py moved to separate `agent/` directory
**File:** `CLAUDE.md`, `docs/spec/05-remote-support.md`, `docs/spec/10-infrastructure.md`
**Issue:** `agent.py` was in `backend/` sharing the same image as the backend. Remote machines only need fastapi + uvicorn + httpx — not the full backend stack (SQLAlchemy, OTel SDK, Alembic, clickhouse-connect, etc.).
**Decision:** Option 2 — separate `agent/` top-level directory with its own `requirements.txt` and `Dockerfile`.
**Fix:** Updated CLAUDE.md project layout, agent dev server command, docker-compose build context (`./agent`), docker-compose key decisions note, and remote deployment scp path.

---

### R-29 — `GRAFANA_URL` set to Docker-internal address, wrong for browser deep-links
**File:** `docs/spec/15-environment.md`, `docs/spec/10-infrastructure.md`
**Issue:** `GRAFANA_URL=http://grafana:3001` — `grafana` is a Docker-internal hostname not resolvable by the user's browser. Port 3001 is also wrong inside Docker (container runs on 3000). Deep-links on the run detail page would 404 in every browser.
**Fix:** Corrected to `http://localhost:3001` (host-mapped port, browser-reachable). Added note that this must be changed to the host IP/hostname for remote access. Added `GRAFANA_URL` to backend service env in docker-compose (was missing entirely).

---

### R-30 — `OTEL_COLLECTOR_ENDPOINT`, `VICTORIAMETRICS_URL`, `AGENT_URL` undocumented in Notes
**File:** `docs/spec/15-environment.md`
**Issue:** Three variables in `.env.example` had no Notes entry explaining what uses them.
**Fix:** Added notes for all three — including the two-consumer clarification for `OTEL_COLLECTOR_ENDPOINT` (sidecar + backend OTel SDK) and the browser-vs-Docker distinction for `GRAFANA_URL`.

---

### R-31 — `SECRET_KEY` and `AGENT_SECRET_KEY` share the same placeholder value
**File:** `docs/spec/15-environment.md`
**Issue:** Both showed `changeme-random-32-bytes` — a user copying the file gets the same value for both secrets, which serve different purposes.
**Fix:** Gave each a distinct placeholder string. Added "Must differ from AGENT_SECRET_KEY / SECRET_KEY" to both Notes entries.

---

### R-28 — Phase 3 spec stale after Phase 1 ClickHouse and S-10 decisions
**File:** `docs/spec/12-phase3.md`
**Issues:**
1. ClickHouse schema documented as Phase 3 work — already created in Phase 1 via `infra/clickhouse/init.sql`
2. Sidecar change showed fan-out to both `otlp` and `kafka` exporters — S-10 decided sidecar should publish to Kafka only; VictoriaMetrics receives via consumer, not direct sidecar push
3. No mention of removing `ch_insert()` from runner.py when Kafka consumer takes over ClickHouse writes
**Fix:** Rewrote 12-phase3.md: added goal statement showing Phase 1 → Phase 3 migration, replaced fan-out pattern with kafka-only sidecar exporter, removed ClickHouse schema (references Phase 1 init.sql), added explicit 7-step migration checklist including ch_insert() removal.

---

### S-10 — Phase 3: route sidecar through Kafka for VictoriaMetrics (and ClickHouse)
**File:** `docs/spec/04-otel-sidecar.md`, `docs/spec/12-phase3.md`
**Current (Phase 1):** Sidecar → OTel Collector → VictoriaMetrics (direct). Sidecar is responsible for retry/buffering if VictoriaMetrics is unavailable. The `retry_on_failure` + `sending_queue` on the OTel Collector is the current mitigation.
**Proposed (Phase 3):** Sidecar → Kafka → consumer → VictoriaMetrics
                                               └→ consumer → ClickHouse
The sidecar publishes to Kafka only. Separate consumers handle VictoriaMetrics and ClickHouse writes independently. The sidecar is fully decoupled from storage backend availability — it only needs Kafka to be reachable.
**Benefits:**
- Sidecar has one responsibility: collect and publish. No retry logic needed on the sidecar.
- Storage backends can be unavailable without affecting sidecar or the run.
- ClickHouse consumer replaces the direct `ch_insert()` write from `runner.py` — cleaner separation of concerns.
- Fan-out to additional consumers (e.g., alerting, export) requires no sidecar changes.
**Phase 3 action:** Update `12-phase3.md` with this architecture. When Kafka arrives, replace the sidecar's `otlp` exporter with a `kafka` exporter. Remove `ch_insert()` from `runner.py` — ClickHouse writes move to the Kafka consumer.

---

### S-07 — OTel disk buffer `/tmp/otel-buffer/{run_id}` never cleaned up
**File:** `docs/spec/04-otel-sidecar.md`, `infra/sidecar.yaml.j2`
**Issue:** The `file_storage` extension writes buffered metrics to `/tmp/otel-buffer/{run_id}/` per run. Unlike the sidecar config file (cleaned up in S-04), this directory is never removed. Over many runs it accumulates stale buffer directories in `/tmp`.
**Status:** Accepted for Phase 1 — the data is small and `/tmp` is ephemeral across reboots. If the central collector was unreachable during a run, the buffer may contain undelivered metrics — deleting it immediately would discard them.
**Action:** Phase 2 — add a cleanup task that removes `/tmp/otel-buffer/{run_id}` once the run reaches a terminal state (`completed`, `failed`, `cancelled`) and the sidecar has confirmed delivery (or after a grace period, e.g. 1 hour post-termination).

---

### S-01 — `hostmetrics` receiver captures benchmarking host, not engine machine
**File:** `docs/spec/04-otel-sidecar.md`, `infra/sidecar.yaml.j2`
**Issue:** The sidecar runs on the benchmarking host (Docker Compose stack). The `hostmetrics` receiver in `sidecar.yaml.j2` therefore captures CPU/memory of the benchmarking host — not the remote GPU server running the engine. For local runs this is harmless; for remote runs the host metrics are meaningless.
**Status:** Accepted limitation for Phase 1. The alternative (co-located sidecar on engine machine) requires deploying `otelcol-contrib` on every remote host, violating the zero-pre-install contract. To be revisited in Phase 2 if remote is a serious use case.
**Action:** Add a comment to `sidecar.yaml.j2` noting that `hostmetrics` reflects the benchmarking host, not the engine host. Add a note to the UI run detail page if `config.host != "localhost"`: *"Host metrics reflect the benchrunner machine, not the engine host."*

---

## Resolved Items

### R-01 — Abstract vs. concrete contradiction on `teardown()` and `is_running()`
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The ABC class definition marked `teardown()` and `is_running()` as `@abstractmethod`, but the spec later described both as concrete methods inherited by all drivers. As written, drivers would be required to implement them, defeating the purpose of the shared concrete implementation.
**Fix:** Removed `@abstractmethod` from both `teardown()` and `is_running()` in the ABC definition. Both are now concrete methods only, with docstrings updated to note: *"Concrete implementation on ABC — not abstract, all drivers inherit this unchanged."*

---

### R-02 — `list_models(host, port)` signature cannot serve LlamaCppDriver
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The ABC signature is `list_models(self, host: str, port: int)`. LlamaCppDriver's described behaviour is to return `[config.model]`, which requires a `RunConfig`. The interface does not provide one.
**Resolution:** LlamaCppDriver returns `[]` — consistent with "no discovery API". Models are always registered manually. The `[config.model]` description in the original spec was misleading and has been corrected in the sync behaviour table: llamacpp → `returns [] — no discovery API`.

---

### R-03 — DB session injection into drivers is undefined
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The `validate_config()` concrete example used `db.query(...)` directly, but drivers are instantiated via `DRIVERS[engine]()` with no session injection. There was no defined mechanism for drivers to access the DB.
**Fix:** Updated `validate_config()` signature to `validate_config(self, config: RunConfig, db: AsyncSession) -> list[str]` throughout — ABC definition, concrete base example, and all per-driver descriptions. Updated `execute_run()` in `03-run-execution.md` call site to `await driver.validate_config(config, db)`. Session is injected at call time, not at construction.

---

### R-04 — OllamaDriver.validate_config() contradicts the "no live engine call" rule
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The general `validate_config()` principle states it checks the DB registry with no live engine call. Ollama's specific validation additionally runs `shutil.which("ollama")` and `ollama list` (subprocess calls). These are not network calls but they are live system calls, and the exception was not acknowledged in the spec.
**Fix:** Added explicit note to OllamaDriver `validate_config()` description: subprocess calls (`shutil.which`, `ollama list`) are intentional local system checks, not network calls. Documented the composition pattern: call `super().validate_config(config, db)` first for the registry check, then append local system checks.

---

### R-05 — `config.id` used as `run_id` in `wait_healthy()` — likely wrong identity
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The managed-mode health URL was built as `/run/{config.id}/health`, treating `RunConfig.id` as the run identifier registered with the agent. `Run.id` and `RunConfig.id` are different objects — run config is a reusable template; run is a single execution. The agent would be polled under the wrong ID, returning 404.
**Fix:** Updated `spawn()` and `wait_healthy()` ABC signatures to accept `run_id: UUID` as an explicit parameter. Fixed the managed-mode URL in `wait_healthy()` to use `run_id` (Run.id) instead of `config.id`. Updated `execute_run()` call sites in `03-run-execution.md` to `driver.spawn(config, run_id)` and `driver.wait_healthy(config, run_id)`. Added clarifying docstring: *"run_id: Run.id (not RunConfig.id) — registered with agent and used in all subsequent agent calls."*

---

### R-06 — RemoteSpawner (`remote.py`) has no spec
**File:** `docs/spec/02-engine-drivers.md`, build order step 4
**Issue:** `remote.py` appears in both the build order and CLAUDE.md project layout but has no corresponding spec section in `02-engine-drivers.md`. It is unclear what `RemoteSpawner` does, what its interface is, and how it relates to the agent control plane.
**Resolution:** Confirmed covered by `05-remote-support.md`. The universal agent architecture (single FastAPI agent on every host, called via httpx) replaces any need for a separate RemoteSpawner class. `remote.py` as a standalone module is unnecessary — remote spawning is handled by the driver's `spawn()` method posting to the agent at `config.host:config.agent_port`. CLAUDE.md layout entry for `remote.py` is a leftover from an earlier design iteration and should be removed at build time.

---

### R-07 — `prometheus_client` dependency undeclared
**File:** `docs/spec/02-engine-drivers.md` (ollama_shim), `docs/spec/00-overview.md` stack
**Issue:** `ollama_shim.py` imports `prometheus_client`, but this package did not appear in the declared stack or any requirements file.
**Fix:** Added `prometheus-client` to the backend stack in `00-overview.md`: *"Metrics shim: prometheus-client — used by ollama_shim.py to expose synthetic Prometheus /metrics on port 9091."*

---

### S-02 — `start_sidecar()` is a sync `def` called from async `execute_run()`
**File:** `docs/spec/04-otel-sidecar.md`
**Issue:** `start_sidecar()` was declared as `def` (synchronous) but called directly inside `async def execute_run()`. The `subprocess.Popen()` call blocks the event loop.
**Fix:** Changed to `async def start_sidecar()` using `asyncio.create_subprocess_exec()`. No blocking calls remain on the async path.

---

### S-03 — `stdout=PIPE, stderr=PIPE` can deadlock
**File:** `docs/spec/04-otel-sidecar.md`
**Issue:** `subprocess.Popen(..., stdout=PIPE, stderr=PIPE)` fills OS pipe buffers if output is not actively drained. `otelcol-contrib` logs continuously — the sidecar would eventually block waiting for the pipe to drain, hanging the process silently.
**Fix:** Changed to `stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL`. otelcol-contrib manages its own log file; we don't need to capture output here.

---

### S-04 — Temp config file `/tmp/otel-sidecar-{run_id}.yaml` never deleted
**File:** `docs/spec/04-otel-sidecar.md`, `docs/spec/03-run-execution.md`
**Issue:** `start_sidecar()` writes a per-run config file to `/tmp` but never deletes it. Over many runs this accumulates stale files.
**Fix:** Changed `start_sidecar()` return type to `tuple[asyncio.subprocess.Process, Path]`. Caller (`execute_run()`) unpacks both and calls `sidecar_config_path.unlink(missing_ok=True)` in the `finally` block after `sidecar_proc.terminate()`. Updated `03-run-execution.md` accordingly.

---

### S-05 — `os.environ["OTEL_COLLECTOR_ENDPOINT"]` raises bare `KeyError`
**File:** `docs/spec/04-otel-sidecar.md`
**Issue:** A missing env var raises `KeyError: 'OTEL_COLLECTOR_ENDPOINT'` with no context about where to set it or what it controls.
**Fix:** Replaced with `os.environ.get(...)` + explicit `RuntimeError("OTEL_COLLECTOR_ENDPOINT is not set — add it to .env or environment")`. Fails fast at run start rather than mid-template render.

---

### S-06 — `jinja2.Template()` silently ignores missing variables
**File:** `docs/spec/04-otel-sidecar.md`
**Issue:** `jinja2.Template(text).render(...)` uses `Undefined` by default — missing template variables render as empty string, producing a syntactically valid but semantically broken sidecar config. The error surfaces only when `otelcol-contrib` fails to start.
**Fix:** Replaced with `jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(text)`. Any missing variable now raises `UndefinedError` at render time, immediately and clearly.

---

### R-25 — OTel Collector `prometheusremotewrite` missing retry config
**File:** `docs/spec/10-infrastructure.md`
**Issue:** The central OTel Collector's `prometheusremotewrite` exporter had no `retry_on_failure` or `sending_queue` settings. Agreed during sidecar review (04-otel-sidecar.md) to add retry config — it was added to the sidecar's exporter but not to the central collector. Transient VictoriaMetrics unavailability would silently drop metrics.
**Fix:** Added `retry_on_failure` (5s/30s/300s) and `sending_queue` (1000) to match the sidecar exporter config.

---

### R-26 — `otel-collector` missing `depends_on: victoriametrics`
**File:** `docs/spec/10-infrastructure.md`
**Issue:** The collector starts and immediately tries to write to VictoriaMetrics. No startup ordering was enforced — on first boot or slow hardware, VictoriaMetrics may not be healthy yet and early metrics are dropped.
**Fix:** Added `depends_on: victoriametrics: condition: service_healthy` to the otel-collector service.

---

### R-27 — `grafana` missing `depends_on: clickhouse`
**File:** `docs/spec/10-infrastructure.md`
**Issue:** Grafana provisions a ClickHouse datasource on startup but had no depends_on for the clickhouse service. If ClickHouse wasn't healthy, datasource provisioning would fail silently.
**Fix:** Added `depends_on: clickhouse: condition: service_healthy` to the grafana service.

---

### R-21 — `bench_run_start_timestamp` referenced in Grafana annotation but never declared
**File:** `docs/spec/09-grafana.md`, `docs/spec/08-metrics-storage.md`
**Issue:** The annotation expression used `bench_run_start_timestamp{run_id=~"$run_id"}` but this metric was not declared in `08-metrics-storage.md`. The annotation would silently produce no data.
**Fix:** Added `bench_run_start_timestamp` to `08-metrics-storage.md` as a Gauge pushed once at `run_started_at`. Also added OTel instrument types (Histogram/Gauge/Counter) for all app-level metrics — required for correct Grafana queries.

---

### R-22 — TTFT Grafana query flattens to single value
**File:** `docs/spec/09-grafana.md`
**Issue:** `avg by (run_id) (bench_request_ttft_ms{...})` with no time window computes a flat average across all scraped values — renders as a horizontal line, not a trend.
**Fix:** Changed to `histogram_quantile(0.50, rate(bench_request_ttft_ms_bucket{...}[2m]))`. Consistent with the p99 latency panel approach. Requires `bench_request_ttft_ms` to be a Histogram instrument (also documented in R-21 fix).

---

### R-23 — Compare page time axis note stale after Phase 1 downscope
**File:** `docs/spec/09-grafana.md`
**Issue:** Note said "compare page time axes expressed as relative seconds since run_started_at" — but the compare page was downscoped to BarChart in Phase 1 (no time axis). Misleading for Phase 1 implementation.
**Fix:** Updated note to Phase 2 context.

---

### R-24 — ClickHouse Grafana datasource not provisioned
**File:** `docs/spec/09-grafana.md`, `docs/spec/10-infrastructure.md`
**Issue:** ClickHouse moved to Phase 1 but Grafana provisioning only declared a VictoriaMetrics datasource. SQL drill-down panels would have no data source to connect to.
**Fix:** Added `datasources/clickhouse.yaml` provisioning file. Added `GF_INSTALL_PLUGINS=grafana-clickhouse-datasource` to Grafana service in docker-compose.

---

### R-19 — "SQLite / PostgreSQL" heading in metrics storage spec
**File:** `docs/spec/08-metrics-storage.md`
**Issue:** Heading still referenced SQLite after the Phase 1 PostgreSQL decision.
**Fix:** Updated to "PostgreSQL (app database)".

---

### R-20 — App-level metrics missing `host` label; scraped metrics showed native-only labels
**File:** `docs/spec/08-metrics-storage.md`
**Issue:** `bench_request_*` metrics were listed without the `host` label. These are pushed by the backend OTel SDK directly (not via sidecar), so `host` is not added automatically by the resource processor — it must be set explicitly in the SDK. Additionally, llamacpp and Ollama metrics were shown with only their native labels (e.g. `{run_id}`) rather than the final sidecar-enriched label set, making the docs misleading for anyone writing Grafana queries.
**Fix:** Added `host` to all app-level metrics. Updated all metric label sets to show the final enriched label set `{run_id, model, engine, host}`. Added explanatory note distinguishing pushed (SDK) vs scraped (sidecar) metrics and where base labels come from in each case.

---

### R-15 — Wizard "Refresh models" passes `?port=` which is not a valid registry filter
**File:** `docs/spec/07-frontend.md`
**Issue:** Step 2 called `GET /api/engines/{engine}/models?host=&port=`. Port is not stored in `EngineModel` and is not a valid filter — models are keyed by engine + host + model_id only.
**Fix:** Corrected to `GET /api/engines/{engine}/models?host={host}`. Added note that the button reads from the DB registry, not the live engine.

---

### R-16 — Ollama `spawn_mode` not locked in the wizard
**File:** `docs/spec/07-frontend.md`
**Issue:** The spawn_mode selector was shown for all engines. Ollama is always attach mode — showing "Managed" as an option would let users create an invalid config that fails at validate_config() with no clear UI explanation.
**Fix:** For Ollama, spawn_mode selector is hidden and locked to "attach". UI displays: "Ollama runs as a system service — always attach mode."

---

### R-17 — Compare page LineChart has no time-series data source (deferred to Phase 2)
**File:** `docs/spec/07-frontend.md`
**Issue:** The compare page specified a Recharts LineChart with X axis as relative seconds since run_started_at. `POST /api/runs/compare` returns aggregates only — no time-series endpoint exists. Fetching all RequestRecords via the paginated endpoint is impractical for multi-run charts.
**Fix:** Phase 1 compare chart downscoped to BarChart (one bar per run) using aggregate data from `POST /api/runs/compare`. Phase 2 adds `GET /api/runs/{id}/timeseries?metric=p99&bucket_s=10` and replaces the BarChart with a LineChart.

---

### R-18 — `EngineModel` has no `is_stale` field but model registry shows stale badge
**File:** `docs/spec/07-frontend.md`, `docs/spec/01-data-models.md`
**Issue:** The model registry page showed a "stale" badge with no backing field on `EngineModel`. "Stale" could not be reliably computed from `last_synced` alone without knowing when the last sync ran.
**Fix:** Added `is_stale: bool` to `EngineModel`. Set to `True` by the sync endpoint when a previously-synced model is absent from the latest sync result. Always `False` for `source="manual"`.

---

### R-11 — Route ordering note missing for `/api/prompts/import` and `/api/prompts/export`
**File:** `docs/spec/06-api-routes.md`
**Issue:** The spec warned about `/api/runs/compare` vs `/api/runs/{id}` ordering but omitted the same warning for `/api/prompts/import` and `/api/prompts/export` vs `/api/prompts/{id}`. FastAPI would silently match `"import"` and `"export"` as the `{id}` parameter without explicit route ordering.
**Fix:** Added ordering note and moved import/export routes above `{id}` routes in the spec.

---

### R-12 — WebSocket closure behaviour unspecified
**File:** `docs/spec/06-api-routes.md`
**Issue:** The WebSocket spec defined the event shape but not when the server closes the connection. A client following the spec would poll indefinitely after run completion.
**Fix:** Added "WebSocket lifecycle" section: final event on terminal state → close 1000; reconnect on unexpected closure; close 1008 if run not found.

---

### R-13 — `DELETE /api/runs/{id}` terminal state behaviour unspecified
**File:** `docs/spec/06-api-routes.md`
**Issue:** No specified behaviour when cancelling a run already in a terminal state — implementation could silently no-op, corrupt state, or vary across runs.
**Fix:** Added: returns 409 if run is already in a terminal state (completed, failed, cancelled).

---

### R-14 — Comparisons share token mechanism unspecified
**File:** `docs/spec/06-api-routes.md`
**Issue:** `GET /api/comparisons/{token}` implied a share token but `POST /api/comparisons` showed no token in the response. A developer building against the spec could not implement shareable links.
**Fix:** Added full request/response shape to `POST /api/comparisons` including token field. Documented token as `secrets.token_urlsafe(16)`, generated at creation, immutable.

---

### R-10 — Agent endpoints unauthenticated
**File:** `docs/spec/05-remote-support.md`, `docs/spec/15-environment.md`
**Issue:** Agent listened on `0.0.0.0:8787` with no API key — any node on the Tailnet could call `POST /spawn` or `DELETE /run/{run_id}`. Tailscale ACL alone is insufficient when the Tailnet includes more than one trusted machine.
**Fix:** Added shared key authentication. Backend sends `X-Agent-Key: <secret>` on every agent call. Agent validates via FastAPI dependency using `secrets.compare_digest()` on all routes except `GET /health`. Key stored as `AGENT_SECRET_KEY` in `.env` — same value required on benchmarking host and all remote agent hosts. Driver httpx calls updated to include the header. Key generation instructions added to `15-environment.md`.
