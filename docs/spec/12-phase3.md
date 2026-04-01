# Inference Benchrunner — Phase 3 (Kafka + ClickHouse)

## DO NOT READ unless explicitly instructed

Add Phase 3 infrastructure only when hitting one of these triggers:
- OTel sidecars losing data during collector outages
- Team needs per-request SQL drill-down queries
- 20+ simultaneous runs with sustained high-frequency metrics

---

## Kafka

Topic: `inference-metrics-raw`
Partitions: 12 (assumes max 12 concurrent runs — increase if needed;
partition count cannot be reduced after creation)
Retention: 7 days

## Sidecar change (add Kafka exporter)

```yaml
exporters:
  otlp:           # existing — keep for VictoriaMetrics path
    endpoint: "..."
  kafka:          # add
    brokers: ["kafka:9092"]
    topic: inference-metrics-raw
    encoding: otlp_proto

service:
  pipelines:
    metrics:
      exporters: [otlp, kafka]   # fan-out to both
```

## ClickHouse consumer

Use `aiokafka` (fits async-first backend, preferred over confluent-kafka-python).
Batch insert every 1000 rows or 5 seconds, whichever comes first.

## ClickHouse schema

```sql
CREATE TABLE inference_requests (
    run_id        String,
    request_id    String,
    model         String,
    engine        String,
    host          String,
    prompt_tokens UInt32,
    gen_tokens    UInt32,
    ttft_ms       Float32,
    latency_ms    Float32,
    tokens_per_sec Float32,
    status        String,
    error_type    Nullable(String),
    started_at    DateTime64(3)
) ENGINE = MergeTree()
ORDER BY (run_id, started_at);
```
