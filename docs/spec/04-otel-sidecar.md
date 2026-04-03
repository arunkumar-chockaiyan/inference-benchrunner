# Inference Benchrunner — OTel Sidecar

## Purpose
Each benchmark run spawns a co-located OTel Collector process on the
benchmarking host. The sidecar starts AFTER warmup completes (run_started_at
marks sidecar start time). It scrapes engine metrics, stamps every metric with
run_id, buffers to disk, and forwards to the central OTel Collector.
The sidecar always runs on the benchmarking host — never on the remote engine machine.

## Sidecar config template (infra/sidecar.yaml.j2)

```yaml
extensions:
  file_storage:
    directory: /tmp/otel-buffer/{{ run_id }}

receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: inference_engine
          scrape_interval: 5s
          static_configs:
            - targets: ['{{ metrics_host }}:{{ metrics_port }}']

  hostmetrics:
    # NOTE (S-01): captures CPU/memory of the benchmarking host — NOT the remote
    # engine machine. For local runs this is useful; for remote runs these metrics
    # reflect the wrong host. Accepted limitation for Phase 1. See docs/review.md S-01.
    collection_interval: 5s
    scrapers:
      cpu:
      memory:

processors:
  batch:
    timeout: 5s
  resource:
    attributes:
      - key: run_id
        value: "{{ run_id }}"
        action: insert
      - key: model
        value: "{{ model }}"
        action: insert
      - key: engine
        value: "{{ engine }}"
        action: insert
      - key: host
        value: "{{ engine_host }}"
        action: insert

exporters:
  otlp:
    endpoint: "{{ central_collector_endpoint }}"
    sending_queue:
      storage: file_storage
      queue_size: 1000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s   # buffer up to 5 min of central collector unavailability

service:
  extensions: [file_storage]
  pipelines:
    metrics:
      receivers:  [prometheus, hostmetrics]
      processors: [batch, resource]
      exporters:  [otlp]
```

## start_sidecar()

```python
from pathlib import Path
import asyncio, jinja2, os

async def start_sidecar(
    run_id: str,
    engine: str,
    model: str,
    metrics_host: str,
    metrics_port: int,
    engine_host: str,
) -> tuple[asyncio.subprocess.Process, Path]:
    # Path resolved relative to source file — safe in Docker
    template_path = Path(__file__).parent.parent / "infra" / "sidecar.yaml.j2"

    # S-06: StrictUndefined raises at render time if any variable is missing —
    # catches template/call-site mismatches immediately instead of silently
    # producing a broken config that fails only when otelcol-contrib starts.
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    template = env.from_string(template_path.read_text())

    # S-05: fail fast with a clear message — KeyError from os.environ[] gives no
    # context about which variable is missing or where to set it.
    endpoint = os.environ.get("OTEL_COLLECTOR_ENDPOINT")
    if not endpoint:
        raise RuntimeError(
            "OTEL_COLLECTOR_ENDPOINT is not set — add it to .env or environment"
        )

    config_text = template.render(
        run_id=run_id,
        model=model,
        engine=engine,
        metrics_host=metrics_host,
        metrics_port=metrics_port,
        engine_host=engine_host,
        central_collector_endpoint=endpoint,
    )
    config_path = Path(f"/tmp/otel-sidecar-{run_id}.yaml")
    config_path.write_text(config_text)

    # S-02: asyncio.create_subprocess_exec — non-blocking, consistent with async execute_run().
    # S-03: DEVNULL instead of PIPE — PIPE buffers fill if not actively drained,
    # blocking the child process. otelcol-contrib logs to its own file; we don't
    # need stdout/stderr here.
    proc = await asyncio.create_subprocess_exec(
        "otelcol-contrib", "--config", str(config_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    # S-04: return config_path — caller (execute_run) must unlink it in finally
    # after proc.terminate(). Leaving /tmp/otel-sidecar-*.yaml files is a leak
    # across runs.
    return proc, config_path
```

## Metrics port by engine

| Engine   | metrics_host | metrics_port | Notes                                  |
|----------|--------------|--------------|----------------------------------------|
| ollama   | localhost    | 9091         | ollama_shim runs on benchmarking host — always localhost regardless of config.host |
| llamacpp | config.host  | config.port  | native /metrics via --metrics flag     |
| vllm     | config.host  | config.port  | native /metrics                        |
| sglang   | config.host  | config.port  | native /metrics                        |

`execute_run()` passes `metrics_host=config.host` for all engines. For Ollama this
equals "localhost" because Ollama is always a local service (validated by
OllamaDriver.validate_config()). The ollama_shim always binds to localhost:9091 on
the benchmarking host — never on a remote machine.

For non-Ollama remote engines: sidecar scrapes the remote host over Tailscale directly.

## Sidecar lifecycle

1. NOT started during warmup
2. Started at run_started_at (after warmup completes)
3. `proc.pid` stored in Run.sidecar_pid
4. Terminated in execute_run() finally block before driver.teardown()
5. Disk buffer at /tmp/otel-buffer/{run_id} covers brief central collector outages
6. Config file /tmp/otel-sidecar-{run_id}.yaml deleted in execute_run() finally block after proc.terminate()

### Caller contract in execute_run() finally block

```python
    finally:
        if ollama_shim:
            ollama_shim.terminate()
        if sidecar_proc:
            sidecar_proc.terminate()
            await sidecar_proc.wait()    # prevent zombie — wait for SIGTERM to be handled
        if sidecar_config_path:
            sidecar_config_path.unlink(missing_ok=True)   # S-04: clean up temp config
        if spawn_result and spawn_result.owned:
            await driver.teardown(config, spawn_result)
```

`sidecar_proc` and `sidecar_config_path` are unpacked from `start_sidecar()`:
```python
        sidecar_proc, sidecar_config_path = await start_sidecar(...)
```
