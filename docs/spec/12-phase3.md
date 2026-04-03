# Inference Benchrunner — Phase 3 (Kafka pipeline)

## DO NOT READ unless explicitly instructed

Add Phase 3 infrastructure only when hitting one of these triggers:
- OTel sidecars losing data during collector outages
- Team needs per-request SQL drill-down queries
- 20+ simultaneous runs with sustained high-frequency metrics

---

## Goal

Decouple the sidecar from storage backends. In Phase 1, the sidecar writes
directly to the OTel Collector → VictoriaMetrics, and runner.py writes directly
to ClickHouse via ch_insert(). In Phase 3, Kafka becomes the single publish
target for the sidecar. Consumers handle all storage writes independently.

```
Phase 1:  sidecar → OTel Collector → VictoriaMetrics
          runner.py → ch_insert() → ClickHouse

Phase 3:  sidecar → Kafka → VictoriaMetrics consumer (OTel Collector or direct)
                          └→ ClickHouse consumer
          runner.py → ch_insert() REMOVED
```

---

## Kafka

Topic: `inference-metrics-raw`
Partitions: 12 (assumes max 12 concurrent runs — increase if needed;
partition count cannot be reduced after creation)
Retention: 7 days

---

## Sidecar change (replace otlp exporter with kafka)

The `otlp` exporter is **replaced** — not kept alongside. VictoriaMetrics receives
metrics via the Kafka consumer, not directly from the sidecar. This is the key
decoupling: the sidecar has one responsibility (publish to Kafka) and is unaffected
by VictoriaMetrics or ClickHouse availability.

```yaml
exporters:
  kafka:
    brokers: ["kafka:9092"]
    topic: inference-metrics-raw
    encoding: otlp_proto
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s

service:
  pipelines:
    metrics:
      exporters: [kafka]   # otlp exporter removed
```

---

## Consumers

### VictoriaMetrics consumer
Reads from `inference-metrics-raw`, forwards to OTel Collector (or direct
prometheus remote write). Replaces the sidecar → OTel Collector → VictoriaMetrics
path from Phase 1.

### ClickHouse consumer
Use `aiokafka` (fits async-first backend, preferred over confluent-kafka-python).
Batch insert every 1000 rows or 5 seconds, whichever comes first.
Replaces `ch_insert()` in runner.py — remove that function when this consumer ships.

---

## ClickHouse schema

No changes — schema already created in Phase 1 via `infra/clickhouse/init.sql`.
See `docs/spec/08-metrics-storage.md` for the current schema.

---

## Migration steps when Phase 3 triggers

1. Deploy Kafka broker (add to docker-compose)
2. Update sidecar template (`infra/sidecar.yaml.j2`) — replace `otlp` exporter with `kafka`
3. Implement and deploy VictoriaMetrics consumer
4. Implement and deploy ClickHouse consumer
5. Remove `ch_insert()` from `backend/runner.py`
6. Remove direct ClickHouse write from `run_one()` in runner.py
7. Verify metrics continuity before removing Phase 1 direct paths
