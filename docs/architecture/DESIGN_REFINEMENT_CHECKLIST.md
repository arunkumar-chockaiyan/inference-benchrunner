# Design Refinement Checklist

Complete walkthrough of InferenceEngineDriver + execute_run() design. Review before Phase 1 implementation.

---

## DRIVERS & AGENT ARCHITECTURE

### ✅ Driver Abstraction
- [x] All 4 engines (Ollama, llama.cpp, vLLM, SGLang) implement InferenceEngineDriver ABC
- [x] Control plane (spawn/health/teardown) routed through agent
- [x] Data plane (stream_prompt/list_models) always direct to engine
- [x] Code path identical for local and remote (host is just config.host)

### ✅ Spawn Modes
- [x] Two modes only: `managed` (agent spawns) and `attach` (pre-running)
- [x] No `auto` mode (simplified)
- [x] Ollama ALWAYS attach mode (enforced in validate_config)
- [x] Location (localhost vs Tailscale IP) separate from spawn_mode

### ✅ Per-Engine Specifics
| Engine | Mode | Health Endpoint | Metrics Port | OpenAI-Compatible |
|--------|------|-----------------|--------------|-------------------|
| Ollama | always attach | /api/tags | 9091 (shim) | ✓ |
| llama.cpp | managed | /health | config.port | ✓ |
| vLLM | managed | /health | config.port | ✓ |
| SGLang | managed | /health | config.port | ✓ |

### ✅ Agent (Control Plane)
- [x] Single agent handles spawn/health/status/teardown for all runs
- [x] Runs on target host (localhost:8787 or Tailscale_IP:8787)
- [x] Identical for local and remote
- [x] Endpoint contract defined

### ✅ Ollama Shim
- [x] Runs on benchmark host (where backend runs)
- [x] Polls localhost:11434/api/ps every 5s
- [x] Exposes synthetic Prometheus metrics on 9091
- [x] Started by execute_run(), killed in finally block
- [x] Only works for local Ollama (not supported remote in Phase 1)

### ✅ Metrics Collection
- [x] Each engine has metrics_port (via get_metrics_port)
- [x] OTel sidecar scrapes every 5s
- [x] Stamps run_id + engine + model labels
- [x] Forwards to central OTel Collector → VictoriaMetrics

---

## EXECUTE_RUN() ORCHESTRATION

### ✅ Phase 1: VALIDATE
- [x] driver.validate_config() checks model in DB registry
- [x] Tailscale warning if remote host doesn't match pattern
- [x] Ollama: rejects spawn_mode != "attach"
- [x] Returns list of errors (empty = valid)

### ✅ Phase 2: SPAWN
- [x] Status: pending → starting
- [x] driver.spawn(config) → SpawnResult
- [x] driver.wait_healthy(config) → polls every 1s until 200 or timeout
- [x] DB: started_at (engine spawn time), server_owned, server_pid

### ✅ Phase 3: OLLAMA SHIM
- [x] if engine == "ollama": subprocess.Popen(ollama_shim.py, env={RUN_ID, MODEL_NAME})
- [x] No-op for other engines

### ✅ Phase 4: WARMUP
- [x] Status: starting → warming_up
- [x] Uses suite.prompts[0].content (first prompt always)
- [x] Runs config.warmup_rounds times (default 3)
- [x] Discards all tokens (run_id="warmup", not counted in metrics)
- [x] DB: warmup_duration_ms
- [x] If warmup fails: status=failed, cleanup runs

### ✅ Phase 5: START SIDECAR
- [x] **CRITICAL:** Sidecar starts AFTER warmup completes
- [x] metrics_port = driver.get_metrics_port(config)
- [x] start_sidecar(run_id, engine, model, metrics_host, metrics_port, engine_host)
- [x] DB: sidecar_pid, run_started_at ← **USE THIS for Grafana alignment, NOT started_at**
- [x] run_started_at marks the moment metrics collection begins

### ✅ Phase 6: RUN BENCHMARK
- [x] Status: warming_up → running
- [x] Concurrency: asyncio.Semaphore(config.concurrency) limits N parallel requests
- [x] Engine watchdog: background task polls is_healthy() every 10s
- [x] Auto-retry: for each prompt, attempt 1..N+1 (N = config.auto_retry, default 2)
- [x] Linear backoff: await asyncio.sleep(1 * attempt) on retry
- [x] Collect metrics via collect_record() → RequestRecord per prompt
- [x] All prompts run in parallel via asyncio.gather()
- [x] Status updates: completed_requests, failed_requests tracking

### ✅ Collect Record
- [x] render_prompt(prompt, config.variable_overrides)
- [x] PromptParams(temp, max_tokens, top_p, timeout_s)
- [x] driver.stream_prompt(rendered, run_id, params) → AsyncIterator[str | ResponseMeta]
- [x] Measure: latency (wall-clock), TTFT (time to first token), token counts
- [x] Prefer engine_tps from ResponseMeta, fall back to wall-clock TPS
- [x] RequestRecord: id, run_id, prompt_id, attempt, status, latency, ttft, tokens, tps, timestamp

### ✅ Exception Handling
- [x] asyncio.CancelledError → status=cancelled, cleanup runs
- [x] Other Exception → status=failed, error_message set, cleanup runs
- [x] teardown() swallows exceptions (no-op if attach)
- [x] Cleanup always runs in finally block

### ✅ Cleanup Order (finally)
1. [x] ollama_shim.terminate() (if Ollama)
2. [x] sidecar.terminate()
3. [x] driver.teardown(config, spawn_result) if owned=True
4. [x] attach mode (owned=False) → no-op, leave engine running

### ✅ Status Transitions
```
pending → starting → warming_up → running → completed
                                         → failed
                                         → cancelled
```
- [x] Each phase updates status in DB
- [x] On exception: status=failed, error_message populated
- [x] CancelledError: status=cancelled

### ✅ Startup Recovery
- [x] recover_stale_runs() called on FastAPI startup
- [x] Scans for runs in starting/warming_up/running
- [x] Attempts agent teardown via agent.get(/run/{id}/status)
- [x] Marks recovered runs as failed with cleanup_warning if agent unreachable

### ✅ Live Progress (WebSocket)
- [x] Per-request event: run_id, status, completed, total, failed, current_tps, elapsed, eta, server_alive
- [x] server_alive = await driver.is_healthy(config) each event

---

## DATA INTEGRITY

### ✅ run_id
- [x] Set at Run creation (UUID)
- [x] Never reused
- [x] Stamped on every OTel metric
- [x] Stored in every RequestRecord
- [x] Passed to stream_prompt() as str(run_id)
- [x] Used for warmup run_id="warmup" (distinct from actual run_id)

### ✅ RequestRecord
- [x] One per prompt per attempt
- [x] Includes attempt number (1, 2, 3, ...)
- [x] Success/failure status
- [x] Latency, TTFT, tokens, TPS
- [x] started_at timestamp

### ✅ Metrics
- [x] OTel sidecar scrapes metrics_host:metrics_port every 5s
- [x] Stamps run_id, engine, model, host labels
- [x] Forwards to central collector → VictoriaMetrics
- [x] Warmup requests NOT scraped (sidecar starts after warmup)

---

## EDGE CASES & DECISIONS

### Q1: Retry Strategy
**Decision:** Catch all exceptions, retry always
**Recommendation:** Filter for retryable exceptions in Phase 1 (timeout, connect errors)
**Non-retryable:** JSON decode, validation errors → fail immediately
**Status:** Ready to implement with improvement

### Q2: Warmup Prompt
**Decision:** Always use suite.prompts[0]
**Why:** Consistent, predictable
**Future:** Add warmup_prompt override in Phase 2 if users request
**Status:** Confirmed

### Q3: Watchdog Interval
**Decision:** 10s default (config.watchdog_interval_s)
**Why:** Reasonable balance, responsive to failures
**Note:** Driver timeout_s is the real safety net
**Status:** Confirmed

### Q4: Warmup Failure Behavior
**Decision:** Fail immediately if any warmup attempt fails
**Why:** Warmup failures indicate infrastructure problems, not transient errors
**Status:** Confirmed

### Q5: Concurrency × Auto-Retry
**Decision:** Independent
**Max concurrent = concurrency × (auto_retry + 1)**
**Example:** concurrency=4, auto_retry=2 → up to 12 concurrent API calls
**Risk:** Could overwhelm weak engines
**Mitigation:** Document; validate in Phase 2 if needed
**Status:** Confirmed

### Q6: Metrics Host
**Decision:** metrics_host = engine_host = config.host
**Why:** Simplicity; separate metrics host not needed in Phase 1
**Status:** Confirmed

---

## FINAL CHECKLIST

### Architecture Decisions ✅
- [x] Driver abstraction pattern (ABC, no modifications for new engines)
- [x] Control plane via agent, data plane direct
- [x] Two spawn modes (managed/attach)
- [x] Ollama always attach
- [x] Location orthogonal to spawn_mode

### Run Execution Flow ✅
- [x] 6 phases (validate → spawn → shim → warmup → sidecar → benchmark)
- [x] Cleanup order (shim → sidecar → engine)
- [x] Exception handling (cancel/fail/cleanup)
- [x] Status transitions
- [x] Startup recovery

### Metrics & Observability ✅
- [x] run_id as spine (never reused)
- [x] run_started_at for Grafana alignment (not started_at)
- [x] Sidecar starts after warmup
- [x] Watchdog monitors engine health
- [x] WebSocket live progress with server_alive

### Data Integrity ✅
- [x] RequestRecord per prompt per attempt
- [x] Attempt tracking for debugging
- [x] OTel metrics stamped with run_id
- [x] Warmup excluded from metrics

### Edge Cases & Improvements ✅
- [x] Retryable exception filtering (improvement)
- [x] Concurrent limit combinatorics documented
- [x] Warmup timing understood
- [x] Phase 2 refinements identified

---

## CONFIDENCE LEVEL

**✅ READY FOR PHASE 1 IMPLEMENTATION**

The spec is:
- Complete ✓
- Implementable as-written ✓
- No architectural blockers ✓
- One small improvement suggested (retryable exceptions) ✓

Proceed to Step 1: Database models + SQLAlchemy setup.

---

**Reviewed:** 2026-03-31
**Status:** Design approved for Phase 1
**Next:** Database schema (Step 1)
