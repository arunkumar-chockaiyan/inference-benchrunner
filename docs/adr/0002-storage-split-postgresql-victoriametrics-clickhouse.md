# ADR-0002: Storage Split (PostgreSQL + VictoriaMetrics + ClickHouse)

**Date:** 2026-03-31
**Updated:** 2026-04-03
**Status:** Accepted

**Context:** InferenceBenchRunner collects three different data types: structured
metadata (runs, prompts, configs), time-series engine metrics (CPU, throughput,
latency), and per-request event rows (for SQL drill-down and comparison).

## Problem

A single database is unsuitable:
- SQL for time-series is inefficient (poor compression, slow range queries)
- Time-series DBs don't handle transactional CRUD well
- Operational metrics need sub-second granularity; metadata doesn't
- Row-level event data needs fast analytical queries by run_id, model, engine

## Decision

Use a **tri-database architecture** from Phase 1:

| Store | Type | Purpose | Retention |
|-------|------|---------|-----------|
| **PostgreSQL** | OLTP SQL | Run configs, prompts, suites, request records, projects | Permanent |
| **VictoriaMetrics** | Time-Series | Engine metrics scraped by OTel sidecar (CPU, memory, tokens/sec) | ~12 months (configurable) |
| **ClickHouse** | Columnar OLAP | Per-request event rows for fast SQL drill-down and comparison | Permanent |

**Data flow:**
1. All structured metadata → PostgreSQL (via SQLAlchemy async)
2. OTel sidecar scrapes engine's `/metrics` endpoint every 5s
3. Sidecar stamps `run_id`, `model`, `engine`, `host` labels on every metric
4. Sidecar forwards to central OTel Collector → VictoriaMetrics
5. `collect_record()` dual-writes each RequestRecord: PostgreSQL + ClickHouse (best-effort)
6. Comparison queries: aggregate stats from PostgreSQL RequestRecords; time-series from VictoriaMetrics; drill-down from ClickHouse

**Phase 3 migration:** Kafka slots in between sidecar and VictoriaMetrics/ClickHouse
as a fanout/resilience layer — no schema changes. `ch_insert()` in runner.py is
removed; ClickHouse writes move to Kafka consumer. See `docs/spec/12-phase3.md`.

## Consequences

**Positive:**
- Each store is optimised for its access pattern
- VictoriaMetrics: 10x compression, fast range queries for Grafana dashboards
- ClickHouse: sub-second analytical queries across millions of request rows
- PostgreSQL: ACID guarantees for run state and metadata
- ClickHouse writes are best-effort — a failure never blocks a benchmark run

**Negative:**
- Three databases to operate and provision
- Comparisons require cross-store coordination (Python-side)
- Eventual consistency on metrics (~10s scrape + batch gap)
- ch_insert() best-effort means ClickHouse may have gaps if the service was down

## Alternatives Considered

1. **PostgreSQL only** — Rejected: time-series queries and columnar analytics both perform poorly
2. **PostgreSQL + InfluxDB** — Rejected: VictoriaMetrics is simpler, more resource-efficient, Prometheus-compatible
3. **ClickHouse only** — Rejected: OLTP workloads (run state, prompt management) need ACID transactions
4. **SQLite for Phase 1** — Rejected: PostgreSQL used from Phase 1 to avoid a migration; SQLite doesn't support async drivers well

## Related

- `run_id` (UUID) is the join key across all three stores
- Schema: `docs/spec/01-data-models.md` (PostgreSQL), `docs/spec/08-metrics-storage.md` (all three)
- ClickHouse init: `infra/clickhouse/init.sql`
- Phase 3 Kafka migration: `docs/spec/12-phase3.md`
