# Inference Benchrunner — Metrics & Storage

## What gets stored where

### PostgreSQL (app database)
All structured data: prompts, suites, run configs, runs, request records,
projects, saved comparisons.

### VictoriaMetrics (time-series)
Aggregated metrics scraped by OTel sidecar from engine /metrics endpoints.
Every metric carries labels: run_id, model, engine, host.

All metrics in VictoriaMetrics carry a consistent base label set:
`{run_id, model, engine, host}`.

- Scraped metrics (vLLM, llama.cpp, SGLang, Ollama shim): base labels added by the
  sidecar's `resource` processor.
- App-level metrics (bench_request_*): base labels must be set explicitly by the
  backend OTel SDK meter at instrument creation time — they are pushed directly to
  the central OTel Collector and do not pass through the sidecar.

Key metrics:
```
# App-level — pushed by backend via OTel SDK (collect_record() in runner.py)
# bench_request_ttft_ms and bench_request_latency_ms are Histogram instruments
# (enables histogram_quantile() in Grafana). bench_tokens_per_second is a Gauge.
bench_request_ttft_ms{run_id, model, engine, host}          # Histogram
bench_request_latency_ms{run_id, model, engine, host}        # Histogram
bench_tokens_per_second{run_id, model, engine, host}         # Gauge
bench_request_errors_total{run_id, model, engine, host, error_type}  # Counter
bench_run_start_timestamp{run_id, model, engine, host}       # Gauge — Unix timestamp
                                                              # pushed once at run_started_at
                                                              # used for Grafana annotations

# vLLM / SGLang native — scraped by sidecar, enriched with base labels
vllm:e2e_request_latency_seconds_bucket{run_id, model, engine, host}
vllm:request_throughput{run_id, model, engine, host}
vllm:gpu_cache_usage_perc{run_id, model, engine, host}
vllm:num_requests_running{run_id, model, engine, host}

# llama.cpp native — scraped by sidecar, enriched with base labels
llamacpp_prompt_tokens_total{run_id, model, engine, host}
llamacpp_tokens_per_second{run_id, model, engine, host}
llamacpp_context_usage_ratio{run_id, model, engine, host}

# GPU (via DCGM exporter or nvidia-smi scrape) — enriched with base labels
DCGM_FI_DEV_GPU_UTIL{run_id, model, engine, host, gpu}
DCGM_FI_DEV_MEM_COPY_UTIL{run_id, model, engine, host, gpu}
DCGM_FI_DEV_FB_USED{run_id, model, engine, host, gpu}

# Ollama synthetic (via ollama_shim) — scraped by sidecar, enriched with base labels
ollama_active_models{run_id, model, engine, host}
ollama_model_vram_gb{run_id, model, engine, host}
```

### ClickHouse (Phase 1)
Row-level per-request event data for SQL drill-down. Written directly from
`collect_record()` in runner.py — no Kafka in Phase 1.

Schema (created via `infra/clickhouse/init.sql` on container start):

```sql
CREATE TABLE IF NOT EXISTS inference_requests (
    run_id         String,
    request_id     String,
    model          String,
    engine         String,
    host           String,
    prompt_tokens  UInt32,
    gen_tokens     UInt32,
    ttft_ms        Nullable(Float32),
    latency_ms     Float32,
    tokens_per_sec Nullable(Float32),
    status         String,
    error_type     Nullable(String),
    started_at     DateTime64(3)
) ENGINE = MergeTree()
ORDER BY (run_id, started_at);
```

Write path: `collect_record()` calls `ch_insert(record, config)` after the
PostgreSQL insert. ClickHouse writes are **best-effort** — a failure logs a
warning but does NOT fail the run or the PostgreSQL write.

Python client: `clickhouse-connect` (async-compatible, official ClickHouse client).

### Kafka (Phase 3 only)
Fanout transport layer. Slots in front of ClickHouse in Phase 3 without
schema changes. Do NOT add until Phase 3 triggers are hit. See 12-phase3.md.
