# QA Spec — Metrics & Storage

Source: `docs/spec/08-metrics-storage.md`, `backend/runner.py` (ch_insert, OTel SDK calls)

---

## OTel metric label completeness

Every metric pushed by the backend OTel SDK must carry the four base labels:
`{run_id, model, engine, host}`.

### Unit test — meter instrument creation

Mock the OTel SDK meter. For each instrument created in `collect_record()`:

| Instrument | Type | Labels required |
|------------|------|----------------|
| `bench_request_ttft_ms` | Histogram | `run_id, model, engine, host` |
| `bench_request_latency_ms` | Histogram | `run_id, model, engine, host` |
| `bench_tokens_per_second` | Gauge | `run_id, model, engine, host` |
| `bench_request_errors_total` | Counter | `run_id, model, engine, host, error_type` |
| `bench_run_start_timestamp` | Gauge | `run_id, model, engine, host` |

Assert each label key is present in the recorded metric attributes.
Assert no metric is recorded without `run_id` — this is the spine invariant.

### bench_run_start_timestamp

- Pushed exactly once per run, at `run_started_at` (not `started_at`)
- Value is Unix timestamp (float seconds)
- Used for Grafana chart alignment — a wrong value misaligns all charts

### bench_request_errors_total

- Incremented for each failed request with `error_type` label set
- `error_type` values: derived from exception class (e.g. `"TimeoutException"`, `"ConnectError"`)

---

## VictoriaMetrics label enrichment

The OTel sidecar's `resource` processor adds base labels to scraped engine metrics.
These tests verify the rendered sidecar config (see `04-otel-sidecar.md`) inserts all four labels.

For scraped metrics (not pushed by the SDK), labels are added by the sidecar resource processor:

| Metric family | Source | Labels added by sidecar |
|---------------|--------|------------------------|
| `vllm:*` | vLLM `/metrics` | `run_id, model, engine, host` |
| `llamacpp_*` | llama.cpp `/metrics` | `run_id, model, engine, host` |
| `ollama_*` | ollama_shim `/metrics` | `run_id, model, engine, host` |
| `DCGM_*` | DCGM exporter | `run_id, model, engine, host` (Phase 2) |

---

## ClickHouse — best-effort write (`test_runner.py`)

### Write succeeds

After `collect_record()` succeeds and saves to PostgreSQL:
- `ch_insert(record, config)` is called
- Verify the ClickHouse `inference_requests` table schema matches:

```sql
run_id, request_id, model, engine, host,
prompt_tokens, gen_tokens, ttft_ms, latency_ms,
tokens_per_sec, status, error_type, started_at
```

### Write fails — run continues

Mock `ch_insert()` to raise an exception:
- `logger.warning()` called with run_id and exception
- PostgreSQL `RequestRecord` is still saved
- Run does NOT transition to `"failed"`
- Subsequent prompts continue executing

### Field mapping

| `RequestRecord` field | ClickHouse column | Type |
|----------------------|-------------------|------|
| `id` | `request_id` | String |
| `run_id` | `run_id` | String |
| `prompt_tokens` | `prompt_tokens` | UInt32 |
| `generated_tokens` | `gen_tokens` | UInt32 |
| `ttft_ms` | `ttft_ms` | Nullable(Float32) |
| `total_latency_ms` | `latency_ms` | Float32 |
| `tokens_per_second` | `tokens_per_sec` | Nullable(Float32) |
| `status` | `status` | String |
| `error_type` | `error_type` | Nullable(String) |
| `started_at` | `started_at` | DateTime64(3) |

### ch_insert order relative to PostgreSQL

Assert `ch_insert()` is called AFTER `await db.insert(record)` (PostgreSQL is primary).

---

## PostgreSQL — primary data store

### RequestRecord completeness

After a successful run, assert for each prompt in the suite:
- Exactly one `RequestRecord` per prompt (with `attempt=1` on first success)
- Retried prompts have `attempt > 1` on the saved record (the last successful one)
- Failed prompts have `status="error"` or `status="timeout"` with `error_message` set

### Run aggregate fields

After `execute_run()` completes:
- `Run.completed_requests` = count of `RequestRecord` rows with `status="success"`
- `Run.failed_requests` = count of `RequestRecord` rows with `status` in `{"error","timeout"}`
- `Run.total_requests` = total prompts in suite

### config_snapshot integrity

`Run.config_snapshot` is a JSON snapshot of `RunConfig` at run start.
Test: mutate the `RunConfig` after run starts → `config_snapshot` unchanged.

---

## Compare endpoint — aggregate computation

`POST /api/runs/compare` computes stats from `RequestRecord` rows.

### p99 metric

- `metric="p99"` → `p99` field is the 99th percentile of `total_latency_ms`
- Test: 100 records with latencies 1–100 ms → p99 ≈ 99 ms

### TTFT metric

- `metric="ttft"` → stats computed from `ttft_ms` column (exclude null values)

### Throughput metric

- `metric="throughput"` → stats computed from `tokens_per_second` column

### Stddev

- `stddev` is standard deviation across all records for the run
- Zero records → `sample_count=0`, other fields null or 0

### Multi-run compare

- Two runs with different `run_id` → separate entries in response
- Stats for run A not contaminated by run B's records (run_id filter)
