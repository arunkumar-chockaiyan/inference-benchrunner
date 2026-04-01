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
      max_elapsed_time: 300s

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
import jinja2, subprocess, os

def start_sidecar(
    run_id: str,
    engine: str,
    model: str,
    metrics_host: str,
    metrics_port: int,
    engine_host: str,
) -> subprocess.Popen:
    # Path resolved relative to source file — safe in Docker
    template_path = Path(__file__).parent.parent / "infra" / "sidecar.yaml.j2"
    template = jinja2.Template(template_path.read_text())
    config_text = template.render(
        run_id=run_id,
        model=model,
        engine=engine,
        metrics_host=metrics_host,
        metrics_port=metrics_port,
        engine_host=engine_host,
        central_collector_endpoint=os.environ["OTEL_COLLECTOR_ENDPOINT"],
    )
    config_path = f"/tmp/otel-sidecar-{run_id}.yaml"
    Path(config_path).write_text(config_text)

    return subprocess.Popen(
        ["otelcol-contrib", "--config", config_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
```

## Metrics port by engine

| Engine   | metrics_host | metrics_port | Notes                                  |
|----------|--------------|--------------|----------------------------------------|
| ollama   | localhost    | 9091         | ollama_shim synthetic metrics          |
| llamacpp | config.host  | config.port  | native /metrics via --metrics flag     |
| vllm     | config.host  | config.port  | native /metrics                        |
| sglang   | config.host  | config.port  | native /metrics                        |

For remote engines: sidecar scrapes the remote host over Tailscale directly.

## Sidecar lifecycle

1. NOT started during warmup
2. Started at run_started_at (after warmup completes)
3. sidecar.pid stored in Run.sidecar_pid
4. Terminated in execute_run() finally block before driver.teardown()
5. Disk buffer at /tmp/otel-buffer/{run_id} covers brief central collector outages
