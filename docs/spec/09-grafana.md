# Inference Benchrunner — Grafana Setup

## Data source
VictoriaMetrics as Prometheus data source.
URL: http://victoriametrics:8428

## Provisioning files
```
infra/grafana/provisioning/
  datasources/victoriametrics.yaml   # auto-configures VictoriaMetrics data source
  datasources/clickhouse.yaml        # auto-configures ClickHouse data source
  dashboards/dashboard.yaml          # tells Grafana to scan dashboards/ dir
  dashboards/bench.json              # importable dashboard, UID: "bench-dashboard"
```

### clickhouse.yaml datasource

```yaml
apiVersion: 1
datasources:
  - name: ClickHouse
    type: grafana-clickhouse-datasource
    url: http://clickhouse:8123
    jsonData:
      defaultDatabase: default
      port: 8123
      server: clickhouse
      username: default
      tlsSkipVerify: true
```

Note: requires the `grafana-clickhouse-datasource` plugin. Add to Grafana service
in docker-compose:
```yaml
environment:
  - GF_INSTALL_PLUGINS=grafana-clickhouse-datasource
```

Dashboard UID "bench-dashboard" must be fixed in bench.json — the run detail
page deep-link depends on it:
  {GRAFANA_URL}/d/bench-dashboard/bench?var-run_id={run_id}

## Dashboard variables
```
run_id = label_values(bench_request_latency_ms, run_id)  [multi-value]
engine = label_values(bench_request_latency_ms, engine)
model  = label_values(bench_request_latency_ms, model)
```

## Key panels

p99 latency:
```promql
histogram_quantile(0.99,
  rate(bench_request_latency_ms_bucket{run_id=~"$run_id"}[2m])
)
```

TTFT p50 over time:
```promql
histogram_quantile(0.50,
  rate(bench_request_ttft_ms_bucket{run_id=~"$run_id"}[2m])
)
```

Tokens per second:
```promql
avg by (run_id) (bench_tokens_per_second{run_id=~"$run_id"})
```

Error rate:
```promql
sum by (run_id) (rate(bench_request_errors_total{run_id=~"$run_id"}[2m]))
```

KV cache utilisation (vLLM/SGLang):
```promql
avg by (run_id) (vllm:gpu_cache_usage_perc{run_id=~"$run_id"})
```

GPU utilisation:
```promql
avg by (run_id) (DCGM_FI_DEV_GPU_UTIL{run_id=~"$run_id"})
```

Request queue depth:
```promql
avg by (run_id) (vllm:num_requests_running{run_id=~"$run_id"})
```

## Time axis alignment

All panels use `run_started_at` (not `started_at`) as the time origin.
`run_started_at` marks the moment warmup completed and the OTel sidecar started —
this is when meaningful metrics begin.

**Scrape gap:** The sidecar config uses `scrape_interval: 5s` and `batch timeout: 5s`,
so the first metric data point arrives approximately 10s after `run_started_at`.
This produces a small gap at the left edge of every panel — expected behaviour.

Each panel should include an annotation at `run_started_at`:

```json
{
  "name": "Benchmark start",
  "expr": "changes(bench_run_start_timestamp{run_id=~\"$run_id\"}[1m]) > 0",
  "step": "60s",
  "titleFormat": "Benchmark started",
  "textFormat": "Warmup complete. Sidecar scraping. First data point follows scrape interval (~10s)."
}
```

**Phase 2 note:** When the compare page LineChart is added (Phase 2), time axes
will be expressed as **relative seconds since run_started_at** so runs started
at different wall-clock times are directly comparable. The `run_started_at`
value is available from the Run DB record for this purpose.

---

## Anonymous access
GF_AUTH_ANONYMOUS_ENABLED=true, GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer.
Appropriate for small trusted team. No login required to view dashboards.
