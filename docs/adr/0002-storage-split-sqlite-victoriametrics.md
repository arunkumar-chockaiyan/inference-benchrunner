# ADR-0002: Storage Split (SQLite for Metadata, VictoriaMetrics for Time-Series)

**Date:** 2026-03-31
**Status:** Accepted
**Context:** InferenceBenchRunner collects two different data types: structured metadata (runs, prompts, configs) and time-series metrics (CPU, memory, throughput).

## Problem

A single database is unsuitable:
- SQL for time-series is inefficient (poor compression, slow range queries)
- Time-series DBs don't handle transactional CRUD well
- Operational metrics need sub-second granularity; metadata doesn't
- OLTP (on-line transaction processing) and OLAP (on-line analytic processing) have conflicting access patterns

## Decision

Use a **dual-database architecture**:

| Store | Type | Purpose | Retention |
|-------|------|---------|-----------|
| **SQLite** (or PostgreSQL) | OLTP SQL | Run configs, prompts, suites, request metadata | Permanent |
| **VictoriaMetrics** | Time-Series | Engine metrics (CPU, memory, tokens/sec) | ~7 days (configurable) |

**Data flow:**
1. All run metadata → SQLite (created at run time)
2. OTel sidecar scrapes engine's `/metrics` endpoint
3. Sidecar stamps `run_id` label on every metric
4. Sidecar forwards to OTel Collector → VictoriaMetrics
5. Comparison queries: JOIN metadata from SQLite + time-series from VictoriaMetrics

## Consequences

**Positive:**
- Efficient time-series compression (VictoriaMetrics achieves 10x compression)
- Fast range queries for comparison dashboards
- Structured metadata is immutable and queryable
- Natural separation of concerns

**Negative:**
- Two databases to operate
- Comparisons require cross-database joins (Python-side coordination)
- Eventual consistency (metric flush delay ~10s)
- Retention policy for VictoriaMetrics must be set explicitly

## Alternatives Considered

1. **ClickHouse only** — Rejected because OLTP overhead; phase 3 addition for drill-down queries
2. **PostgreSQL + influxDB** — Rejected because overkill; VictoriaMetrics is simpler and more cloud-native
3. **Single SQLite with TimescaleDB extension** — Rejected because tight coupling; metrics are ephemeral

## Related

- `run_id` (UUID) is the join key: stamped on every metric and every RequestRecord row
- Phase 3: ClickHouse added for row-level event drill-down (only when needed)
