# Inference Benchrunner — Metrics & Storage

## What gets stored where

### SQLite / PostgreSQL (app database)
All structured data: prompts, suites, run configs, runs, request records,
projects, saved comparisons.

### VictoriaMetrics (time-series)
Aggregated metrics scraped by OTel sidecar from engine /metrics endpoints.
Every metric carries labels: run_id, model, engine, host.

Key metrics:
```
# App-level pushed by backend via OTel SDK
bench_request_ttft_ms{run_id, model, engine}
bench_request_latency_ms{run_id, model, engine}
bench_tokens_per_second{run_id, model, engine}
bench_request_errors_total{run_id, model, engine, error_type}

# vLLM / SGLang native
vllm:e2e_request_latency_seconds_bucket{run_id, model, engine}
vllm:request_throughput{run_id, model, engine}
vllm:gpu_cache_usage_perc{run_id, model, engine}
vllm:num_requests_running{run_id, model, engine}

# llama.cpp native
llamacpp_prompt_tokens_total{run_id}
llamacpp_tokens_per_second{run_id}
llamacpp_context_usage_ratio{run_id}

# GPU (via DCGM exporter or nvidia-smi scrape)
DCGM_FI_DEV_GPU_UTIL{run_id, gpu}
DCGM_FI_DEV_MEM_COPY_UTIL{run_id, gpu}
DCGM_FI_DEV_FB_USED{run_id, gpu}

# Ollama synthetic (via ollama_shim)
ollama_active_models{run_id}
ollama_model_vram_gb{run_id, model}
```

### ClickHouse (phase 3 only)
Row-level event data for SQL drill-down. See 12-phase3.md.
Do NOT add until Phase 3 triggers are hit.
