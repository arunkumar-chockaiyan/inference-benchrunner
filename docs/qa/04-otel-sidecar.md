# QA Spec — OTel Sidecar

Source: `docs/spec/04-otel-sidecar.md`, `backend/sidecar.py`, `infra/sidecar.yaml.j2`

---

## Template rendering (`test_sidecar.py`)

### All variables substituted

Call `start_sidecar()` with known inputs. Read the rendered config file before
the subprocess is started. Assert:

| Template variable | Input value | Rendered in config |
|-------------------|-------------|-------------------|
| `{{ run_id }}` | `"abc-123"` | Appears in `file_storage.directory`, `resource.attributes` |
| `{{ model }}` | `"llama3:8b"` | Appears in `resource.attributes` |
| `{{ engine }}` | `"ollama"` | Appears in `resource.attributes` |
| `{{ metrics_host }}` | `"localhost"` | Appears in `scrape_configs.targets` |
| `{{ metrics_port }}` | `9091` | Appears in `scrape_configs.targets` |
| `{{ engine_host }}` | `"localhost"` | Appears in `resource.attributes` |
| `{{ central_collector_endpoint }}` | env var value | Appears in `exporters.otlp.endpoint` |

### StrictUndefined — missing variable fails fast

Pass a template with a variable omitted from the render call.
Assert `jinja2.UndefinedError` raised at render time (not silently broken config).

### Missing OTEL_COLLECTOR_ENDPOINT

Unset env var, call `start_sidecar()`.
Assert `RuntimeError("OTEL_COLLECTOR_ENDPOINT is not set")` raised before any subprocess.

---

## Resource labels in rendered config

The sidecar's `resource` processor must insert all four base labels.
Assert rendered YAML contains:

```yaml
processors:
  resource:
    attributes:
      - key: run_id
        value: "<run_id>"
        action: insert
      - key: model
        value: "<model>"
        action: insert
      - key: engine
        value: "<engine>"
        action: insert
      - key: host
        value: "<engine_host>"
        action: insert
```

---

## Sidecar lifecycle (`test_sidecar.py`)

### Subprocess created with correct args

Mock `asyncio.create_subprocess_exec`. Assert called with:
```python
("otelcol-contrib", "--config", "/tmp/otel-sidecar-{run_id}.yaml")
```
And `stdout=DEVNULL, stderr=DEVNULL` — PIPE must NOT be used.

### Config file path

Assert config written to `/tmp/otel-sidecar-{run_id}.yaml` (unique per run).

### Config file cleanup (caller contract)

In `execute_run()` tests:
- Assert `config_path.unlink()` is called in `finally` block even if run fails
- Assert `sidecar_proc.wait()` is called after `terminate()` (no zombie process)

### Two runs simultaneously

Two runs with different `run_id` values should create two separate config files
and two separate buffer directories (`/tmp/otel-buffer/{run_id}`).

---

## Metrics port routing

| Engine | Expected `metrics_host` | Expected `metrics_port` |
|--------|------------------------|------------------------|
| Ollama | `"localhost"` (always) | `9091` (ollama_shim) |
| llamacpp | `config.host` | `config.port` |
| vLLM | `config.host` | `config.port` |
| SGLang | `config.host` | `config.port` |

Test: call `driver.get_metrics_port(config)` for each engine and assert value.

**Ollama special case**: even if `config.host` is `"localhost"`, the shim always
binds to `localhost:9091` on the benchmarking host. Verify `execute_run()` passes
`metrics_host="localhost"` for Ollama runs regardless of `config.host`.

---

## Disk buffer configuration

Assert rendered config includes:
```yaml
exporters:
  otlp:
    sending_queue:
      storage: file_storage
      queue_size: 1000
    retry_on_failure:
      enabled: true
      max_elapsed_time: 300s
```

This ensures up to 5 minutes of central collector unavailability is tolerated.

---

## Sidecar start timing (integration)

In `execute_run()` integration test:
- Track call order of: warmup requests, `start_sidecar()`, benchmark requests
- Assert `start_sidecar()` is called AFTER all warmup requests complete
- Assert `run_started_at` is set in the same logical step as `start_sidecar()`
- Warmup requests must not appear in any OTel metrics (run_id="warmup" is used)
