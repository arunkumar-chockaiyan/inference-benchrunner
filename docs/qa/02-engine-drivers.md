# QA Spec — Engine Drivers

Source: `docs/spec/02-engine-drivers.md`, `backend/drivers/`

---

## ABC contract tests (`test_base.py`)

Every driver must satisfy these tests. Run against all four driver classes.

### spawn() contract

| Scenario | Expected |
|----------|----------|
| `spawn_mode="managed"` | POST to agent `/spawn`; returns `SpawnResult(owned=True)` |
| `spawn_mode="attach"` | No agent call; returns `SpawnResult(owned=False, pid=None)` |
| Agent unreachable in managed mode | Raises `RuntimeError` (not silently returns) |
| `run_id` passed to spawn | Matches `Run.id` (not `RunConfig.id`) in agent payload |

### teardown() contract

| Scenario | Expected |
|----------|----------|
| `owned=True` | DELETE to agent `/run/{run_id}`; confirms stopped |
| `owned=False` | No HTTP call made; logs and returns |
| Agent unreachable | Swallows exception; does NOT re-raise (finally block safety) |
| Agent returns 404 | Treated as success (idempotent teardown) |

### wait_healthy() contract

| Scenario | Expected |
|----------|----------|
| Engine healthy within timeout | Returns without error |
| Engine never healthy (timeout) | Raises `TimeoutError` |
| Per-poll errors (ConnectionRefused) | Swallowed; polling continues |
| `managed` mode | Polls agent `/run/{run_id}/health` |
| `attach` mode | Polls `health_url()` directly (no agent) |

### stream_prompt() contract

| Assertion | Rationale |
|-----------|-----------|
| Final item in stream is `ResponseMeta` | collect_record() depends on this |
| String chunks yielded before `ResponseMeta` | Token streaming order |
| `ResponseMeta.prompt_tokens` > 0 | Non-zero for any real prompt |
| `ResponseMeta.generated_tokens` > 0 | Non-zero for any non-empty response |
| `httpx.TimeoutException` raised on timeout | collect_record() retry logic |
| Engine called directly — no agent URL in request | Data plane isolation |

### validate_config() contract

| Scenario | Expected |
|----------|----------|
| Valid config, model in registry | Returns `[]` |
| Model not in `EngineModel` registry | Returns list with error string |
| Invalid port (0 or >65535) | Returns error |
| Remote host not Tailscale address | Returns warning string |
| Never makes live engine call | Verified by asserting no httpx calls |

### is_healthy() contract

- Returns `True` on HTTP 200 from health endpoint
- Returns `False` on any exception (connection refused, timeout, non-200)
- Never raises — caller relies on boolean return

---

## OllamaDriver (`test_ollama.py`)

### spawn()
- Always returns `SpawnResult(owned=False)` regardless of `spawn_mode` in config
- Makes no HTTP call to agent

### health_url()
- Returns `http://{host}:{port}/api/tags` (not `/health`)

### validate_config()
- `spawn_mode != "attach"` → error: `"Ollama is a system service — use spawn_mode='attach'"`
- Checks `shutil.which("ollama")` — mock this in tests
- Checks `ollama list` output for model name — mock subprocess

### stream_prompt()
Mock `httpx.AsyncClient.post` to return NDJSON chunks:
```json
{"response": "Hello", "done": false}
{"response": " world", "done": false}
{"response": "", "done": true, "prompt_eval_count": 5, "eval_count": 3, "eval_duration": 1500000000}
```
Assert:
- Two string chunks yielded: `"Hello"`, `" world"`
- Final item: `ResponseMeta(prompt_tokens=5, generated_tokens=3, engine_tps≈2.0)`
- TPS = `eval_count / (eval_duration / 1e9)` = `3 / 1.5` = `2.0`

### list_models()
Mock GET `/api/tags` → `{"models": [{"name": "llama3:8b"}, {"name": "mistral:7b"}]}`
Assert: returns `["llama3:8b", "mistral:7b"]`

### get_metrics_port()
Returns `9091` always (ollama_shim port)

### ollama_shim (separate test)
- Shim exposes Prometheus metrics on port 9091
- Scrapes `http://localhost:11434/api/ps`
- `ollama_active_models{run_id=...}` = number of loaded models
- `ollama_model_vram_gb{run_id=..., model=...}` = VRAM in GB
- Failure to reach `/api/ps` is swallowed silently (metrics unchanged)

---

## LlamaCppDriver (`test_llamacpp.py`)

### spawn()
Mock agent `POST /spawn`. Assert command includes:
`"./llama-server --model {model} --port {port} --metrics --ctx-size 4096"`

### stream_prompt()
Mock POST `/completion` NDJSON:
```json
{"content": "tok1", "stop": false}
{"content": "tok2", "stop": true, "tokens_evaluated": 10, "tokens_predicted": 2,
 "timings": {"predicted_per_second": 45.0}}
```
Assert: `ResponseMeta(prompt_tokens=10, generated_tokens=2, engine_tps=45.0)`

### list_models()
- With `config.model` set: returns `[config.model]`
- Without model: returns `[]`

### get_metrics_port()
Returns `config.port`

### validate_config()
- Model path missing → error
- `spawn_mode="managed"` valid for llamacpp (unlike Ollama)

---

## VllmDriver (`test_vllm.py`)

### stream_prompt()
Must send `{"stream": true, "stream_options": {"include_usage": true}}`.
Mock SSE stream with final usage chunk:
```json
{"choices": [...], "usage": {"prompt_tokens": 8, "completion_tokens": 12}}
```
Assert: `ResponseMeta(prompt_tokens=8, generated_tokens=12, engine_tps=None)`

**Critical**: `stream_options.include_usage` must be in the request body — verify it.

### list_models()
Mock GET `/v1/models` → `{"data": [{"id": "meta-llama/Llama-3-8B"}]}`

### get_metrics_port()
Returns `config.port`

---

## SGLangDriver (`test_sglang.py`)

- Identical `stream_prompt()` and `ResponseMeta` shape as VllmDriver
- Spawn command: `python -m sglang.launch_server --model-path {model} --port {port}`
- `list_models()`: GET `/v1/models`
- Verify SGLang uses same OpenAI-compatible SSE format

---

## Driver registry (`test___init__.py`)

```python
def test_get_driver_known():
    assert isinstance(get_driver("ollama"), OllamaDriver)
    assert isinstance(get_driver("vllm"), VllmDriver)

def test_get_driver_unknown():
    with pytest.raises(ValueError, match="Unknown engine"):
        get_driver("unknown_engine")
```

---

## Cross-driver invariants (parametrized)

```python
@pytest.mark.parametrize("engine", ["ollama", "llamacpp", "vllm", "sglang"])
async def test_stream_ends_with_response_meta(engine, mock_engine_http):
    driver = get_driver(engine)
    chunks = [c async for c in driver.stream_prompt("hello", "run-1", params)]
    assert isinstance(chunks[-1], ResponseMeta)

@pytest.mark.parametrize("engine", ["ollama", "llamacpp", "vllm", "sglang"])
async def test_teardown_noop_when_not_owned(engine):
    driver = get_driver(engine)
    result = SpawnResult(owned=False, pid=None, run_id="x", agent_host="localhost", agent_port=8787)
    # Should not raise, should not make HTTP calls
    await driver.teardown(config, result)
```
