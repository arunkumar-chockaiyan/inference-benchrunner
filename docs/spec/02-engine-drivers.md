# Inference Benchrunner — Engine Drivers

## File layout

```
backend/
  drivers/
    __init__.py     # exports DRIVERS registry + get_driver()
    base.py         # InferenceEngineDriver ABC + all dataclasses
    ollama.py       # OllamaDriver  (attach-only — Ollama is a system service)
    llamacpp.py     # LlamaCppDriver
    vllm.py         # VllmDriver
    sglang.py       # SGLangDriver
  agent.py          # FastAPI agent — manages engine lifecycle for all runs
```

---

## InferenceEngineDriver ABC

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

class InferenceEngineDriver(ABC):

    # --- Lifecycle (control plane — via agent) ---

    @abstractmethod
    async def spawn(self, config: RunConfig) -> SpawnResult:
        """Start or attach to inference server via agent.
        managed mode: POST to agent /spawn → SpawnResult(owned=True)
        attach mode:  no agent call → SpawnResult(owned=False)
        Agent host = config.host (localhost or Tailscale addr), port = config.agent_port.
        """

    async def wait_healthy(
        self,
        config: RunConfig,
        timeout: int | None = None,
    ) -> None:
        """Poll agent /run/{run_id}/health every 1s until healthy.
        Agent polls engine localhost internally — benchmark host never hits engine port.
        attach mode: calls health_url() directly (no agent).
        Swallows all per-poll errors. Raises TimeoutError when deadline exceeded.
        Uses config.health_timeout_s (default 180s) if timeout not passed.
        """
        deadline = time.monotonic() + (timeout or config.health_timeout_s or 180)

        if config.spawn_mode == "managed":
            url = f"http://{config.host}:{config.agent_port}/run/{config.id}/health"
        else:
            url = self.health_url(config)  # attach mode — direct engine call

        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, timeout=5)
                if resp.status_code == 200:
                    return
            except Exception:
                pass  # ConnectionRefused, timeout, 503 — expected during startup
            await asyncio.sleep(1)

        raise TimeoutError(
            f"{config.engine} on {config.host}:{config.port} did not become "
            f"healthy within {timeout or config.health_timeout_s or 180}s"
        )

    def health_url(self, config: RunConfig) -> str:
        """Direct engine health endpoint — used for attach mode only.
        Override in OllamaDriver (uses /api/tags instead of /health).
        """
        return f"http://{config.host}:{config.port}/health"

    @abstractmethod
    async def teardown(self, config: RunConfig, result: SpawnResult) -> None:
        """Stop engine if owned. No-op if result.owned is False (attach mode).
        managed mode: DELETE http://{agent_host}:{agent_port}/run/{run_id}
        attach mode:  log and return — never kill a server we didn't start.
        """

    @abstractmethod
    async def is_running(self, config: RunConfig, result: SpawnResult) -> bool:
        """Check if engine is still alive.
        managed mode: GET http://{agent_host}:{agent_port}/run/{run_id}/status
        attach mode:  GET health_url() — non-blocking, returns False on any error.
        """

    # --- Inference (data plane — direct to engine) ---

    @abstractmethod
    async def stream_prompt(
        self,
        prompt: str,
        run_id: str,
        params: PromptParams | None = None,
    ) -> AsyncIterator[str | ResponseMeta]:
        """Stream response tokens as str chunks.
        Always calls engine directly — never routed through agent.
        Final item is always ResponseMeta with exact token counts.
        Raises httpx.TimeoutException if params.timeout_s exceeded.
        execute_run() owns RequestRecord construction from this stream.
        """

    # --- Discovery (data plane — direct to engine) ---

    @abstractmethod
    async def list_models(self, host: str, port: int) -> list[str]:
        """Return available models for this engine at host:port.
        Calls engine directly. Used in wizard Step 2 before RunConfig exists.
        """

    @abstractmethod
    async def validate_config(self, config: RunConfig) -> list[str]:
        """Pre-flight check. Returns list of error strings (empty = valid).
        Called by POST /api/runs before anything is spawned.
        """

    @abstractmethod
    def get_metrics_port(self, config: RunConfig) -> int:
        """Return the port this engine exposes Prometheus /metrics on.
        Called by execute_run() to configure OTel sidecar.
        """
```

---

## Driver registry

```python
DRIVERS: dict[str, type[InferenceEngineDriver]] = {
    "ollama":   OllamaDriver,
    "llamacpp": LlamaCppDriver,
    "vllm":     VllmDriver,
    "sglang":   SGLangDriver,
}

def get_driver(engine: str) -> InferenceEngineDriver:
    if engine not in DRIVERS:
        raise ValueError(f"Unknown engine: {engine}. Valid: {list(DRIVERS)}")
    return DRIVERS[engine]()
```

---

## OllamaDriver — attach-only

Ollama is a system service. The agent never manages its lifecycle.
spawn_mode is ALWAYS "attach" for Ollama — validated in validate_config().

- **spawn()**: always returns `SpawnResult(owned=False, pid=None, ...)`. No agent call.
- **health_url()**: overrides default → `http://{host}:{port}/api/tags`
- **wait_healthy()**: inherited — uses health_url() directly (attach mode path)
- **stream_prompt()**: POST `/api/generate` with `{"model":..., "prompt":..., "stream":true}`.
  Each chunk is JSON. Final chunk when `done:true` → yield:
  ```python
  ResponseMeta(
      prompt_tokens    = chunk["prompt_eval_count"],
      generated_tokens = chunk["eval_count"],
      engine_tps       = chunk["eval_count"] / (chunk["eval_duration"] / 1e9),
      raw              = chunk,
  )
  ```
- **teardown()**: always no-op (owned=False). Logs and returns.
- **list_models()**: GET `/api/tags` → parse `.models[].name`
- **get_metrics_port()**: returns 9091 (ollama_shim port)
- **validate_config()**:
  - Rejects spawn_mode != "attach" with error: "Ollama is a system service — use spawn_mode='attach'"
  - Checks ollama binary exists: `shutil.which("ollama")`
  - Checks model is pulled: `ollama list`

### Ollama metrics shim

Spawned by execute_run() alongside the run (not by OllamaDriver.spawn()).
Killed in execute_run() finally block. Env vars: RUN_ID, MODEL_NAME.

```python
# backend/drivers/ollama_shim.py
import time, os
import httpx
from prometheus_client import start_http_server, Gauge

RUN_ID     = os.environ["RUN_ID"]
MODEL_NAME = os.environ["MODEL_NAME"]

active_models = Gauge("ollama_active_models", "Loaded models",  ["run_id"])
model_vram_gb = Gauge("ollama_model_vram_gb", "VRAM used (GB)", ["run_id", "model"])

def collect():
    try:
        r = httpx.get("http://localhost:11434/api/ps", timeout=3).json()
        models = r.get("models", [])
        active_models.labels(run_id=RUN_ID).set(len(models))
        for m in models:
            vram = m.get("size_vram", 0) / 1e9
            model_vram_gb.labels(run_id=RUN_ID, model=m["name"]).set(vram)
    except Exception:
        pass

start_http_server(9091)
while True:
    collect()
    time.sleep(5)
```

---

## LlamaCppDriver

- **spawn()**: managed mode → POST to agent with command:
  `./llama-server --model {model} --port {port} --metrics --ctx-size 4096`
- **wait_healthy()**: inherited — agent path for managed, direct for attach
- **stream_prompt()**: POST `/completion` with `{"prompt":..., "n_predict":..., "stream":true}`.
  Final chunk when `stop:true` → yield:
  ```python
  ResponseMeta(
      prompt_tokens    = chunk["tokens_evaluated"],
      generated_tokens = chunk["tokens_predicted"],
      engine_tps       = chunk["timings"]["predicted_per_second"],
      raw              = chunk,
  )
  ```
- **teardown()**: DELETE to agent if owned, no-op if attach.
- **list_models()**: returns `[config.model]` if set, else `[]` ("enter model path manually")
- **get_metrics_port()**: returns `config.port` (same port, --metrics flag)
- **validate_config()**: checks model path set, port valid, Tailscale warning if remote.

---

## VllmDriver

- **spawn()**: managed mode → POST to agent with command:
  `python -m vllm.entrypoints.openai.api_server --model {model} --port {port}`
- **wait_healthy()**: inherited — agent path for managed, direct for attach
- **stream_prompt()**: POST `/v1/chat/completions` with:
  ```json
  {"stream": true, "stream_options": {"include_usage": true}}
  ```
  `stream_options: include_usage: true` is required — otherwise usage is null.
  Final chunk before `[DONE]` → yield:
  ```python
  ResponseMeta(
      prompt_tokens    = chunk["usage"]["prompt_tokens"],
      generated_tokens = chunk["usage"]["completion_tokens"],
      engine_tps       = None,   # vLLM does not report internal TPS
      raw              = chunk["usage"],
  )
  ```
- **teardown()**: DELETE to agent if owned, no-op if attach.
- **list_models()**: GET `/v1/models` → parse `.data[].id`
- **get_metrics_port()**: returns `config.port`
- **validate_config()**: model set, port valid, Tailscale warning if remote.

---

## SGLangDriver

Same OpenAI-compatible API as vLLM. Identical stream_prompt() and ResponseMeta.

- **spawn()**: managed mode → POST to agent with command:
  `python -m sglang.launch_server --model-path {model} --port {port}`
- **wait_healthy()**: inherited
- **stream_prompt()**: identical to VllmDriver
- **teardown()**: DELETE to agent if owned, no-op if attach.
- **list_models()**: GET `/v1/models`
- **get_metrics_port()**: returns `config.port`
- **validate_config()**: same as VllmDriver.

---

## Metrics port by engine

| Engine   | metrics_host | metrics_port | Notes                                  |
|----------|--------------|--------------|----------------------------------------|
| ollama   | localhost    | 9091         | ollama_shim synthetic metrics          |
| llamacpp | config.host  | config.port  | native /metrics via --metrics flag     |
| vllm     | config.host  | config.port  | native /metrics                        |
| sglang   | config.host  | config.port  | native /metrics                        |

Sidecar scrapes remote engine metrics over Tailscale directly.

---

## teardown() — concrete implementation on ABC

Not abstract — all drivers inherit this. No driver-specific override needed.

```python
async def teardown(
    self,
    config: RunConfig,
    result: SpawnResult,
) -> None:
    """Stop engine if owned. No-op if attach mode (result.owned=False).
    Swallows agent errors — teardown is in finally block, must not mask
    original run exception. Sets cleanup_warning on Run if agent unreachable.
    """
    if not result.owned:
        logger.info(
            "attach mode — leaving %s:%s running", config.host, config.port
        )
        return

    url = (
        f"http://{result.agent_host}:{result.agent_port}"
        f"/run/{result.run_id}"
    )
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(url, timeout=15)
        if resp.status_code not in (200, 404):
            logger.warning(
                "teardown: agent returned %s for run %s",
                resp.status_code, result.run_id,
            )
    except Exception as e:
        # Swallow — must not mask original exception in finally block
        logger.error(
            "teardown: could not reach agent for run %s: %s",
            result.run_id, e,
        )
        # execute_run() sets cleanup_warning on the Run record after catching this


## Agent DELETE /run/{run_id} — behaviour contract

- Sends SIGTERM to engine process, waits up to 10s, then SIGKILL
- Idempotent: 200 if process killed OR was already dead
- 404 only if run_id was never registered with this agent instance
- Response: {"stopped": bool, "method": "sigterm"|"sigkill"|"already_dead"}
```

## recover_stale_runs() — backend startup task

Called once on backend startup. Scans for runs stuck in running/warming_up
and attempts agent teardown. Marks them failed if agent doesn't know the run.

```python
async def recover_stale_runs():
    """Called on backend startup. Recovers runs left in-progress after a crash."""
    stale = await db.query(Run).filter(
        Run.status.in_(["running", "warming_up", "starting"])
    ).all()

    for run in stale:
        config = await db.get(RunConfig, run.config_id)
        agent_url = f"http://{config.host}:{config.agent_port}"
        try:
            async with httpx.AsyncClient() as client:
                # Check if agent knows this run
                resp = await client.get(
                    f"{agent_url}/run/{run.id}/status", timeout=5
                )
            if resp.json().get("running"):
                # Agent has it — tear it down
                await client.delete(f"{agent_url}/run/{run.id}", timeout=15)

            await update_run_status(
                run.id, "failed",
                error="Run was in-progress when backend restarted"
            )
        except Exception:
            # Agent unreachable — mark failed with cleanup warning
            await db.update(run,
                status="failed",
                error_message="Run was in-progress when backend restarted",
                cleanup_warning="Agent unreachable during recovery — engine may still be running",
            )

    if stale:
        logger.warning("Recovered %d stale runs on startup", len(stale))
```

---

## is_running() and is_healthy() — concrete methods on ABC

Not abstract — all drivers inherit both. No driver-specific override needed.

```python
async def is_running(self, config: RunConfig, result: SpawnResult) -> bool:
    """Process-level liveness check via agent. Fast.
    managed: GET agent /run/{run_id}/status → {"running": bool}
    attach:  always returns True — no PID available, health check is
             the only real signal for attach mode (see is_healthy()).
    Returns False on any error — agent unreachable = treat as dead.
    """
    if not result.owned:
        return True  # attach mode — assume alive, is_healthy() is the signal

    url = (
        f"http://{result.agent_host}:{result.agent_port}"
        f"/run/{result.run_id}/status"
    )
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5)
        return resp.json().get("running", False)
    except Exception:
        return False  # agent unreachable = treat process as dead

async def is_healthy(self, config: RunConfig) -> bool:
    """HTTP health endpoint check. Non-blocking is_running() equivalent.
    Always calls engine directly — not via agent.
    Used for: mid-run watchdog, attach mode liveness, run detail page.
    Returns False on any error instead of raising.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.health_url(config), timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
```

### When each is used

| method | caller | why |
|--------|--------|-----|
| `is_running()` | `recover_stale_runs()` | Process check — did engine survive backend restart? |
| `is_healthy()` | `execute_run()` watchdog | HTTP check — is engine still serving mid-benchmark? |
| `is_healthy()` | `GET /api/runs/{id}` | Live server health for run detail page |
| `is_healthy()` | WebSocket events | `server_alive` field in live progress stream |
| `is_healthy()` | attach mode | No PID — health endpoint is only liveness signal |

---

## list_models() — role clarification

list_models() is called ONLY by the sync endpoint POST /api/engines/{engine}/models/sync.
It is NOT called live from the wizard. The wizard reads from the EngineModel DB registry.

```
Planning time:  wizard → GET /api/engines/{engine}/models → DB (EngineModel registry)
Sync time:      user triggers sync → POST .../sync → driver.list_models() → upsert DB
Runtime:        validate_config() → DB registry (no live engine call)
```

### Sync behaviour per engine

| Engine   | list_models() behaviour                          | sync trigger    |
|----------|--------------------------------------------------|-----------------|
| Ollama   | GET /api/tags → parse .models[].name             | user-triggered  |
| vLLM     | GET /v1/models → parse .data[].id                | user-triggered  |
| SGLang   | GET /v1/models → parse .data[].id                | user-triggered  |
| llamacpp | returns [] — no discovery API                    | no-op           |

### validate_config() — model check against DB registry

Model validation no longer requires a live engine. Works for both managed
and attach mode:

```python
async def validate_config(self, config: RunConfig) -> list[str]:
    errors = []

    # Check model exists in registry for this engine + host
    known = await db.query(EngineModel).filter(
        EngineModel.engine  == config.engine,
        EngineModel.host    == config.host,
        EngineModel.model_id == config.model,
    ).first()

    if not known:
        errors.append(
            f"Model '{config.model}' not found in registry for "
            f"{config.engine} on {config.host}. "
            f"Sync models or add manually via /api/engines/{config.engine}/models."
        )

    # Tailscale warning for remote hosts
    if os.environ.get("TAILSCALE_ENABLED") and config.host != "localhost":
        is_tailscale = (
            config.host.endswith(".ts.net") or
            config.host.startswith("100.")
        )
        if not is_tailscale:
            errors.append(
                f"Warning: '{config.host}' does not look like a Tailscale address."
            )

    return errors
```
