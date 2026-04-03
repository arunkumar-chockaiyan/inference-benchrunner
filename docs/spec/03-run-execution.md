# Inference Benchrunner — Run Execution Engine

## File locations

| Function | File |
|---|---|
| `execute_run()`, `render_prompt()` | `backend/services/runner.py` |
| `collect_record()` | `backend/services/collector.py` |
| `ch_insert()` | `backend/services/clickhouse.py` |
| `start_sidecar()` | `backend/services/sidecar.py` |

## execute_run()

```python
async def execute_run(run_id: UUID, config: RunConfig, suite: PromptSuite):
    run = await db.get(Run, run_id)
    driver = get_driver(config.engine)
    spawn_result: SpawnResult | None = None
    sidecar_proc: asyncio.subprocess.Process | None = None
    sidecar_config_path: Path | None = None
    ollama_shim: subprocess.Popen | None = None

    try:
        # 1. Validate config before touching any processes
        errors = await driver.validate_config(config, db)
        if errors:
            raise ValueError(f"Invalid config: {'; '.join(errors)}")

        # 2. Spawn or attach to inference server (via agent or direct)
        await update_run_status(run_id, "starting")
        spawn_result = await driver.spawn(config, run_id)      # Run.id, not RunConfig.id
        await driver.wait_healthy(config, run_id)
        await db.update(run,
            server_owned=spawn_result.owned,
            server_pid=spawn_result.pid,
            started_at=datetime.utcnow(),
        )

        # 3. Start Ollama shim if needed (Ollama has no /metrics endpoint)
        if config.engine == "ollama":
            ollama_shim = subprocess.Popen(
                ["python", "drivers/ollama_shim.py"],
                env={**os.environ, "RUN_ID": str(run_id), "MODEL_NAME": config.model},
            )

        # 4. Warmup rounds — sidecar NOT yet started
        #    Metrics excluded from Grafana. Duration logged for UI visibility.
        await update_run_status(run_id, "warming_up")
        warmup_start = time.perf_counter()
        warmup_prompt = suite.prompts[0].content
        for _ in range(config.warmup_rounds):
            async for _ in driver.stream_prompt(
                warmup_prompt, run_id="warmup", params=None
            ):
                pass  # consume and discard — warmup excluded from metrics
        warmup_ms = (time.perf_counter() - warmup_start) * 1000
        await db.update(run, warmup_duration_ms=warmup_ms)

        # 5. Start OTel sidecar — only after warmup completes
        #    run_started_at marks this moment — use for Grafana chart alignment
        metrics_port = driver.get_metrics_port(config)
        sidecar_proc, sidecar_config_path = await start_sidecar(
            run_id=str(run_id),
            engine=config.engine,
            model=config.model,
            metrics_host=config.host,
            metrics_port=metrics_port,
            engine_host=config.host,
        )
        await db.update(run,
            sidecar_pid=sidecar_proc.pid,
            run_started_at=datetime.utcnow(),
        )

        # 6. Run benchmark suite
        await update_run_status(run_id, "running")
        semaphore = asyncio.Semaphore(config.concurrency)

        async def run_one(prompt: Prompt):
            async with semaphore:
                for attempt in range(1, config.auto_retry + 2):
                    try:
                        record = await collect_record(
                            driver, config, prompt, run_id, attempt
                        )
                        await db.insert(record)
                        try:
                            await ch_insert(record, config)  # best-effort
                        except Exception as e:
                            logger.warning("ClickHouse insert failed run=%s: %s", run_id, e)
                        await increment_completed(run_id)
                        return
                    except (
                        httpx.TimeoutException,
                        httpx.ConnectError,
                        httpx.RemoteProtocolError,
                        asyncio.TimeoutError,
                    ) as e:
                        # Transient — worth retrying with linear backoff
                        if attempt > config.auto_retry:
                            await record_error(run_id, prompt.id, attempt, e)
                            await increment_failed(run_id)
                            return
                        await asyncio.sleep(1 * attempt)  # linear backoff
                    except Exception as e:
                        # Non-retryable (JSON decode, driver error, etc.) — fail immediately
                        await record_error(run_id, prompt.id, attempt, e)
                        await increment_failed(run_id)
                        return

        await asyncio.gather(*[run_one(p) for p in suite.prompts])
        await update_run_status(run_id, "completed")

    except asyncio.CancelledError:
        await update_run_status(run_id, "cancelled")
        raise  # CancelledError falls through to finally — cleanup always runs

    except Exception as e:
        await update_run_status(run_id, "failed", error=str(e))
        raise

    finally:
        # Always clean up — order: shim → sidecar → engine
        if ollama_shim:
            ollama_shim.terminate()
        if sidecar_proc:
            sidecar_proc.terminate()
            await sidecar_proc.wait()    # prevent zombie — wait for SIGTERM to be handled
        if sidecar_config_path:
            sidecar_config_path.unlink(missing_ok=True)   # S-04: delete temp config
        if spawn_result and spawn_result.owned:
            await driver.teardown(config, spawn_result)
        # owned=False → attach mode — leave engine running
```

---

## collect_record()

execute_run() owns RequestRecord construction. Drivers only stream tokens.

```python
async def collect_record(
    driver: InferenceEngineDriver,
    config: RunConfig,
    prompt: Prompt,
    run_id: UUID,
    attempt: int,
) -> RequestRecord:
    rendered = render_prompt(prompt, config.variable_overrides)
    params   = PromptParams(
        temperature = config.temperature,
        max_tokens  = config.max_tokens,
        top_p       = config.top_p,
        timeout_s   = config.request_timeout_s,
    )

    start            = time.perf_counter()
    first_token_time = None
    chunks: list[str] = []
    meta: ResponseMeta | None = None

    async for chunk in driver.stream_prompt(rendered, str(run_id), params):
        if isinstance(chunk, ResponseMeta):
            meta = chunk  # exact counts from engine
        else:
            if first_token_time is None and chunk.strip():
                first_token_time = time.perf_counter()
            chunks.append(chunk)

    end      = time.perf_counter()
    total_ms = (end - start) * 1000
    ttft_ms  = (first_token_time - start) * 1000 if first_token_time else None

    # prefer engine-reported counts; fall back to approximation
    prompt_tokens    = meta.prompt_tokens    if meta else len(rendered.split())
    generated_tokens = meta.generated_tokens if meta else len(chunks)
    wall_tps         = generated_tokens / (end - start) if end > start else None

    return RequestRecord(
        id                = uuid4(),
        run_id            = run_id,
        prompt_id         = prompt.id,
        attempt           = attempt,
        status            = "success",
        ttft_ms           = ttft_ms,
        total_latency_ms  = total_ms,
        prompt_tokens     = prompt_tokens,
        generated_tokens  = generated_tokens,
        tokens_per_second = meta.engine_tps or wall_tps,  # prefer engine TPS
        started_at        = datetime.utcnow(),
    )
```

---

## render_prompt()

```python
def render_prompt(prompt: Prompt, overrides: dict[str, str]) -> str:
    variables = {**prompt.variables, **overrides}
    text = prompt.content
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", value)
    return text
```

---

## Run status transitions

```
pending → starting → warming_up → running → completed
                                          → failed
                                          → cancelled
```

- `starting`: agent spawned engine (or attached), wait_healthy() running
- `warming_up`: warmup requests firing, sidecar not yet started
- `running`: warmup done, sidecar up, benchmark in progress
- `completed`: all prompts processed
- `failed`: unhandled exception — error_message populated
- `cancelled`: asyncio.CancelledError received via DELETE /api/runs/{id}

## Cleanup order (finally block)

1. ollama_shim (if Ollama run)
2. OTel sidecar
3. Engine via agent teardown (only if spawn_result.owned=True)

## Backend startup

Call recover_stale_runs() on FastAPI startup event before accepting requests:

```python
@app.on_event("startup")
async def startup():
    await recover_stale_runs()
```

See 02-engine-drivers.md for recover_stale_runs() implementation.

---

## engine_watchdog() — mid-run health monitor

Runs as a background task during the benchmark phase. Polls is_healthy()
every config.watchdog_interval_s seconds (default 10). Cancels the run
immediately if the engine becomes unhealthy — prevents all remaining prompts
from burning through their full retry budget against a dead engine.

```python
async def engine_watchdog(
    driver: InferenceEngineDriver,
    config: RunConfig,
    run_id: UUID,
) -> None:
    """Background task — cancels run if engine becomes unhealthy."""
    while True:
        await asyncio.sleep(config.watchdog_interval_s)
        if not await driver.is_healthy(config):
            logger.error(
                "Engine health check failed for run %s — failing run", run_id
            )
            raise RuntimeError("Engine became unhealthy during benchmark")
```

### Integration in execute_run() step 6

Replace the bare `asyncio.gather` with watchdog-wrapped version:

```python
        # 6. Run benchmark suite with engine watchdog
        await update_run_status(run_id, "running")
        semaphore = asyncio.Semaphore(config.concurrency)

        async def run_one(prompt: Prompt):
            ...  # unchanged

        watchdog = asyncio.create_task(
            engine_watchdog(driver, config, run_id)
        )
        try:
            await asyncio.gather(
                *[run_one(p) for p in suite.prompts],
                watchdog,
            )
        except RuntimeError as e:
            if "unhealthy" in str(e):
                await update_run_status(
                    run_id, "failed",
                    error="Engine became unhealthy during benchmark"
                )
                raise
        finally:
            watchdog.cancel()  # always cancel watchdog when prompts complete
```

### WebSocket live progress — add server_alive field

is_healthy() result included in every WebSocket event:

```json
{
  "run_id": "uuid",
  "status": "running",
  "completed": 42,
  "total": 100,
  "failed": 1,
  "current_tps": 847.3,
  "elapsed_seconds": 34,
  "eta_seconds": 22,
  "server_alive": true
}
```
