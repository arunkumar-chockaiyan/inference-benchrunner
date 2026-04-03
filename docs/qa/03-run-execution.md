# QA Spec — Run Execution Engine

Source: `docs/spec/03-run-execution.md`, `backend/runner.py`

---

## render_prompt() (`test_runner.py`)

### Basic substitution

| Input | Overrides | Expected output |
|-------|-----------|-----------------|
| `"Hello {{name}}"` | `{"name": "Alice"}` | `"Hello Alice"` |
| `"{{a}} and {{b}}"` | `{"a": "X", "b": "Y"}` | `"X and Y"` |
| `"No vars"` | `{}` | `"No vars"` |

### Override precedence

- Prompt default: `{"name": "world"}`
- `config.variable_overrides`: `{"name": "Alice"}`
- Expected: `"Hello Alice"` — override wins over default

### Partial substitution

- Template: `"Hello {{name}}, you are {{age}}"`, only `name` in variables
- `{{age}}` placeholder remains in output (no error raised)

### No mutation

- Original `prompt.variables` dict is not modified after `render_prompt()`

---

## collect_record() (`test_runner.py`)

### TTFT measurement

- Mock `stream_prompt()` to yield: `["", "", "first_real_token", "more"]` then `ResponseMeta`
- Whitespace-only chunks do NOT set `first_token_time`
- TTFT is measured from first non-whitespace, non-empty chunk
- `ttft_ms = (first_token_time - start) * 1000`

### Total latency

- Total latency spans from request start to final `ResponseMeta` receipt
- Includes TTFT + all subsequent tokens

### Token count preference

| Scenario | Expected source |
|----------|----------------|
| `ResponseMeta` present | Use `meta.prompt_tokens`, `meta.generated_tokens` |
| `ResponseMeta` absent | Fallback: word count of rendered prompt / chunk count |

### TPS preference

| Engine | `engine_tps` | Expected `tokens_per_second` |
|--------|-------------|------------------------------|
| Ollama | provided | use `engine_tps` |
| llamacpp | provided | use `engine_tps` |
| vLLM | `None` | use wall-clock TPS |
| SGLang | `None` | use wall-clock TPS |

### RequestRecord fields

Assert all fields populated correctly:
- `id`: new UUID (not reused)
- `run_id`: matches input `run_id`
- `prompt_id`: matches `prompt.id`
- `attempt`: matches input `attempt`
- `status`: `"success"` on normal completion
- `ttft_ms`: `None` only if no non-empty token was yielded
- `started_at`: within 1 second of `datetime.utcnow()`

---

## execute_run() — lifecycle (`test_runner.py`)

### Status progression

Mock all drivers and DB. Assert `Run.status` transitions in order:
1. `"starting"` — after `spawn()` called
2. `"warming_up"` — during warmup loop
3. `"running"` — after sidecar starts
4. `"completed"` — after all prompts processed

### Warmup exclusion from metrics

- Warmup requests call `stream_prompt(run_id="warmup", ...)`
- `collect_record()` is NOT called during warmup
- `warmup_duration_ms` is set after warmup loop

### Sidecar starts after warmup

- Assert `start_sidecar()` is called AFTER warmup loop, not before
- `run_started_at` is set immediately after `start_sidecar()` returns
- `sidecar_pid` stored in Run

### Concurrency bounded by semaphore

- `config.concurrency = 2`, suite has 10 prompts
- Assert max 2 concurrent `stream_prompt()` calls at any moment
- Use a mock that counts concurrent calls

### Ollama shim lifecycle

- `config.engine = "ollama"`: shim is started, terminated in `finally`
- Other engines: shim is NOT started

### Error handling

| Scenario | Expected |
|----------|----------|
| `validate_config()` returns errors | Run transitions to `"failed"` before any spawn |
| `spawn()` raises | Run transitions to `"failed"`; cleanup runs |
| Engine becomes unhealthy mid-run | Watchdog cancels run → `"failed"` |
| `asyncio.CancelledError` | Run transitions to `"cancelled"` |
| ClickHouse insert fails | Warning logged; run continues; PostgreSQL record saved |

### Cleanup order (finally block)

Mock all subprocesses and agents. Assert termination order:
1. `ollama_shim.terminate()` (if Ollama run)
2. `sidecar_proc.terminate()` + `await sidecar_proc.wait()`
3. `sidecar_config_path.unlink()` (temp file deleted)
4. `driver.teardown()` (only if `spawn_result.owned=True`)

### Attach mode teardown safety

- `spawn_result.owned = False` → `driver.teardown()` never calls agent DELETE
- Agent process is left running after the run

---

## engine_watchdog() (`test_runner.py`)

### Cancels run on unhealthy engine

- Mock `is_healthy()` to return `True` for first 2 polls, then `False`
- Assert watchdog raises `RuntimeError("Engine became unhealthy...")`
- Assert `asyncio.gather()` propagates this and run goes to `"failed"`

### Cancelled when prompts complete

- After `asyncio.gather()` returns normally, watchdog task is cancelled
- Assert no `CancelledError` propagates to caller

### Interval respected

- Watchdog sleeps `config.watchdog_interval_s` between polls (default 10s)
- Use `asyncio.sleep` mock to verify interval

---

## recover_stale_runs() (`test_runner.py`)

### Stale run with live agent

- Seed DB with `Run(status="running", ...)`
- Mock agent `GET /run/{id}/status` → `{"running": true}`
- Assert agent `DELETE /run/{id}` called
- Assert run transitions to `"failed"` with error message

### Stale run with dead agent

- Mock agent unreachable (connection refused)
- Assert run marked `"failed"` with `cleanup_warning` set

### Clean startup (no stale runs)

- No runs in `running/warming_up/starting`
- Assert no agent calls made

---

## auto_retry behaviour

| Scenario | Attempt | Expected |
|----------|---------|----------|
| First attempt succeeds | 1 | Record saved, no retry |
| First fails (TimeoutException), second succeeds | 2 | Record saved with `attempt=2` |
| All retries exhausted (`auto_retry=2`, 3 attempts fail) | 3 | Error recorded, `failed_requests` incremented |
| Non-retryable exception (JSON decode error) | 1 | Fail immediately, no retry |

Backoff: assert `asyncio.sleep(1 * attempt)` called between retries.
