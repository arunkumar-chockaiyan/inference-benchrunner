# execute_run() — Design Review & Questions

## Overview

`execute_run()` is the core orchestrator that:
1. Validates config
2. Spawns or attaches to engine
3. Runs warmup rounds (discarded)
4. Starts OTel sidecar (marking run_started_at)
5. Executes prompt suite with concurrency + auto-retry
6. Cleans up in order: shim → sidecar → engine
7. Monitors engine health via watchdog

---

## Key Design Points ✅

### 1. **Sidecar Starts AFTER Warmup** (Phase 5)
- Warmup primes KV cache, GPU memory
- Sidecar starts only after warmup completes
- **Critical:** `run_started_at` marks sidecar start, not engine spawn
  - Use `run_started_at` for Grafana chart alignment
  - `started_at` marks engine spawn (includes warmup noise)

### 2. **Warmup Uses First Prompt** (Phase 4)
```python
warmup_prompt = suite.prompts[0].content
for _ in range(config.warmup_rounds):
    async for _ in driver.stream_prompt(warmup_prompt, run_id="warmup", params=None):
        pass  # discard
```
- Always uses suite[0], not a separate warmup prompt
- Discards tokens completely
- Runs with `run_id="warmup"` (not the actual run_id)
- Duration logged but metrics are not collected

### 3. **Concurrency via Semaphore** (Phase 6)
```python
semaphore = asyncio.Semaphore(config.concurrency)

async def run_one(prompt):
    async with semaphore:
        # request happens here
```
- Limits N concurrent requests
- Default: 1 (sequential)
- Each prompt waits for slot, then fires independently

### 4. **Auto-Retry with Linear Backoff** (Phase 6)
```python
for attempt in range(1, config.auto_retry + 2):
    # attempt 1, 2, ..., config.auto_retry + 1
    try:
        record = await collect_record(...)
        return
    except Exception:
        if attempt > config.auto_retry:
            record_error(run_id, prompt_id, attempt, e)
            increment_failed()
            return
        await asyncio.sleep(1 * attempt)  # 1s, 2s, 3s, ...
```
- Default `config.auto_retry = 2` → up to 3 attempts
- Linear backoff: 1s, 2s, 3s, ... seconds
- Failed requests recorded with attempt number and error

### 5. **Engine Watchdog Monitors Health** (Phase 6)
```python
watchdog = asyncio.create_task(engine_watchdog(driver, config, run_id))

async def engine_watchdog(...):
    while True:
        await asyncio.sleep(config.watchdog_interval_s)  # default 10s
        if not await driver.is_healthy(config):
            raise RuntimeError("Engine became unhealthy during benchmark")
```
- Polls `driver.is_healthy()` every 10s (default)
- Non-blocking HTTP health check
- If unhealthy, cancels ALL remaining prompts immediately
- Prevents wasting time on dead engine

### 6. **Cleanup Order Matters** (finally block)
1. **ollama_shim** (if Ollama)
2. **sidecar** (OTel collector)
3. **engine** (via agent if owned=True)

Why order?
- Shim needs to stop before terminating backend
- Sidecar needs to flush metrics before collector dies
- Engine should be last — cleanup warnings set if agent unreachable

### 7. **Exception Handling**
- `CancelledError`: status=cancelled, falls through to finally (cleanup always runs)
- Other exceptions: status=failed, error_message set, falls through to finally
- `teardown()` swallows its own exceptions (no-op if attach mode)

### 8. **Metrics Collection (collect_record)**
```python
async for chunk in driver.stream_prompt(rendered, str(run_id), params):
    if isinstance(chunk, ResponseMeta):
        meta = chunk  # exact token counts from engine
    else:
        if first_token_time is None and chunk.strip():
            first_token_time = time.perf_counter()
        chunks.append(chunk)
```
- Driver streams token chunks and final ResponseMeta
- Orchestrator measures latency + TTFT
- Prefers engine-reported TPS, falls back to wall-clock
- RequestRecord captures: latency, TTFT, tokens, TPS, attempt, prompt_id, run_id

---

## Design Questions & Ambiguities ❓

### Q1: **Params vs Config Override in collect_record()**
```python
params = PromptParams(
    temperature = config.temperature,
    max_tokens  = config.max_tokens,
    top_p       = config.top_p,
    timeout_s   = config.request_timeout_s,
)
```

**Question:** Can per-prompt overrides of temperature/max_tokens/top_p be specified?
- Currently, all prompts in a suite use same params from config
- Variable injection (render_prompt) handles text, but not inference params
- **Should we support:** `prompt.param_overrides: dict[str, float]` per prompt?
- Or keep it simple: suite-wide params in Phase 1, per-prompt in Phase 2?

**Recommendation:** Keep suite-wide in Phase 1. Document for Phase 2.

---

### Q2: **Warmup Always Uses First Prompt**
```python
warmup_prompt = suite.prompts[0].content
```

**Question:** Is this the right choice?
- Pros: Consistent, predictable, easy
- Cons: What if suite[0] is short and doesn't prime cache properly?
- What if user wants different warmup prompt?

**Options:**
1. **Keep as spec:** Always suite[0] (current)
2. **Add warmup_prompt to RunConfig:** Explicit override
3. **Average all suite prompts:** More representative but harder to measure
4. **Use suite[0] unless RunConfig.warmup_prompt set**

**Recommendation:** Keep spec as-is. If users report cache misses, add override in Phase 2.

---

### Q3: **Retry on What Exceptions?**
```python
except Exception as e:
    if attempt > config.auto_retry:
        record_error(...)
    else:
        await asyncio.sleep(1 * attempt)
```

**Question:** What exceptions should trigger retry?
- `httpx.TimeoutException` (timeout_s exceeded)? **YES, always retry**
- `httpx.ConnectError` (engine unreachable)? **YES, always retry**
- Other networking? **YES**
- JSON decode error? **NO, retry probably won't help**
- Custom driver exception? **depends on message**

**Current spec:** Catches all `Exception`, retries regardless.

**Better approach?** Define retry-able exceptions:
```python
RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    asyncio.TimeoutError,
)

try:
    record = await collect_record(...)
except RETRYABLE as e:
    if attempt > config.auto_retry:
        record_error(...)
    else:
        await asyncio.sleep(1 * attempt)
except Exception as e:
    # non-retryable — fail immediately
    record_error(...)
    increment_failed()
    return
```

**Recommendation:** Implement retryable exception filtering in Phase 1. Prevents wasted retry attempts on non-recoverable errors.

---

### Q4: **Watchdog Interval Timing**
```python
watchdog_interval_s: int  # engine health check interval (default: 10)
```

**Question:** Is 10s the right default?
- If you have 100 prompts at 1s each, watchdog sleeps through entire run (10s > 100s)
- If you have 2 prompts at 60s each, watchdog checks health at: 10s, 20s, 30s, ... (good)
- What if engine dies mid-request? Watchdog won't catch it until next check.

**Current behavior:** Watchdog runs in parallel with prompts. If engine dies:
- Mid-request (40s): Watchdog might not notice until 10s later (at 50s)
- Driver's timeout will catch it (config.request_timeout_s default 120s)
- So driver timeout is the real safety net

**Question:** Should watchdog interval be adaptive or smaller?
- Adaptive: scale with average request latency? (harder)
- Smaller: 5s or 1s for more responsive failure detection? (more polling)

**Recommendation:** Keep 10s default. Document that driver timeout_s is the real safety net. If needed, add `watchdog_interval_s` per RunConfig for tuning.

---

### Q5: **Warmup Exceptions**
```python
warmup_prompt = suite.prompts[0].content
for _ in range(config.warmup_rounds):
    async for _ in driver.stream_prompt(warmup_prompt, run_id="warmup", params=None):
        pass
```

**Question:** What if warmup fails?
- Currently: exception propagates, run status=failed, cleanup runs
- Is this the right behavior?

**Options:**
1. **Current (spec):** Fail immediately if any warmup attempt fails
2. **Retry warmup:** Allow auto_retry attempts on warmup
3. **Continue anyway:** Log warning, skip warmup, continue to phase 6
4. **Partial warmup:** If 2/3 warmup rounds succeed, continue

**Recommendation:** Keep spec as-is (fail immediately). Warmup failures are usually infrastructure problems (engine not ready), not transient. User should investigate before retrying run.

---

### Q6: **Concurrent Requests + Auto-Retry Combinatorics**
```python
concurrency = 4  # 4 parallel requests
auto_retry = 2   # up to 3 attempts each
# max concurrent attempts = 4 × 3 = 12 simultaneous API calls
```

**Question:** Could this overwhelm the engine?
- If concurrency=10, auto_retry=3 → up to 30 concurrent attempts
- Engine might OOM or timeout

**Current spec:** No guardrails. Trust user to tune.

**Recommendation:** Document the relationship. Suggest:
- For small/weak engines: concurrency ≤ 2, auto_retry ≤ 1
- For large engines: concurrency ≤ 8, auto_retry ≤ 3

Add validation in Phase 1? Or Phase 2 when we have GPU metrics?

---

### Q7: **RequestRecord Attempt Tracking**
```python
attempt: int  # 1, 2, or 3 (if auto_retry=2)
```

**Question:** How is `attempt` used downstream?
- Stored in RequestRecord
- Useful for: debugging (retries indicate instability), filtering (only show attempt=1)
- Should UI filter by attempt? Or show all with attempt indicator?

**Recommendation:** Store attempt, but don't enforce filtering in Phase 1. Add UI filtering in Phase 2 (compare page).

---

### Q8: **Sidecar Timing vs Warmup Duration**
```
T=0:   warmup_start
T=5:   warmup done, run_started_at = now, sidecar starts
T=5+N: sidecar first metric arrives (after scrape interval + batch delay)
```

**Question:** Is there a gap between sidecar start and first metric?
- Spec: sidecar config has `scrape_interval: 5s`, `batch timeout: 5s`
- So first metric arrives ~10s after sidecar starts
- Grafana chart shows gap between run_started_at and first data point

**Is this acceptable?** Yes. Documented. Sidecar startup overhead.

**Better messaging?** In Grafana tooltip: "Metrics collection started at run_started_at; first data point after scrape interval."

---

### Q9: **Status Update Granularity**
Current status updates:
- pending (set by POST /api/runs)
- starting (phase 2)
- warming_up (phase 4)
- running (phase 6)
- completed / failed / cancelled

**Question:** Are there intermediate states users care about?
- "healthcheck in progress"? (part of starting)
- "sidecar starting"? (part of running)

**Recommendation:** Current granularity is good for Phase 1. If UI shows "stuck in starting for 10 minutes", can add more detail in Phase 2.

---

### Q10: **Metrics Host vs Engine Host Ambiguity**
```python
start_sidecar(
    run_id=str(run_id),
    engine=config.engine,
    model=config.model,
    metrics_host=config.host,  # ← where to scrape from?
    metrics_port=metrics_port,
    engine_host=config.host,   # ← same as metrics_host?
)
```

**Question:** Are `metrics_host` and `engine_host` always the same?
- For local: localhost
- For remote: Tailscale IP

**Current spec:** Yes, both are config.host.

**Edge case:** What if metrics endpoint is on different host than engine port?
- E.g., separate metrics collection VM?

**Recommendation:** Keep them same for Phase 1. If needed, add `metrics_host` as separate field in Phase 2.

---

## Summary: Design is Sound

The spec is well-designed. The 6-phase flow, cleanup order, watchdog, auto-retry, and status transitions are all solid. Most questions above are about future phases or edge cases.

### **For Phase 1 Implementation:**
1. ✅ Keep warmup as-is (suite[0])
2. ✅ Implement retryable exception filtering (small improvement)
3. ✅ Document concurrency × auto_retry combinatorics
4. ✅ Keep watchdog interval at 10s default
5. ✅ Store attempt number, don't filter in Phase 1
6. ✅ metrics_host = engine_host = config.host

### **For Phase 2 Refinement:**
- Per-prompt param overrides?
- Adaptive watchdog interval?
- UI filtering by attempt?
- Better metrics scrape gap messaging?

---

**Confidence Level: High** — The spec is implementable as-written. No blockers for Phase 1.
