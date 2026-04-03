# ADR-0003: OTel Sidecar Per Run (Benchmarking Host, Not Engine Machine)

**Date:** 2026-03-31
**Updated:** 2026-04-03
**Status:** Accepted

**Context:** InferenceBenchRunner spawns short-lived inference engines for each
run and must collect per-engine metrics (CPU, memory, throughput, latency) tagged
by run_id for Grafana dashboards.

## Problem

If a single central OTel collector scrapes all running engines:
- Collector becomes a bottleneck for parallel runs
- Difficult to namespace metrics by `run_id` without a registration mechanism
- Hard to clean up scrape targets when a run ends
- Requires dynamic scrape target discovery

## Decision

**Each run spawns its own OTel sidecar** (`otelcol-contrib` subprocess) from a
Jinja2 template (`infra/sidecar.yaml.j2`). The sidecar always runs on the
**benchmarking host** — never on the remote engine machine.

**Lifecycle:**
1. `execute_run()` renders the Jinja2 template with `run_id`, `model`, `engine`,
   `metrics_host`, `metrics_port`, `engine_host`
2. Config written to `/tmp/otel-sidecar-{run_id}.yaml`
3. `start_sidecar()` spawns `otelcol-contrib --config=...` as an asyncio subprocess
4. Sidecar starts AFTER warmup completes (`run_started_at` marks this moment)
5. Sidecar scrapes engine's `/metrics` at `metrics_host:metrics_port` every 5s
6. Resource processor stamps `run_id`, `model`, `engine`, `host` on every metric
7. Metrics forwarded to central OTel Collector → VictoriaMetrics
8. On cleanup: `sidecar_proc.terminate()` + `await sidecar_proc.wait()` + config file unlinked

**Benchmarking host placement rationale:**
- Remote engine machines require zero pre-installation beyond the agent
- Sidecar lifetime is bound to `execute_run()` — same process, same cleanup path
- Scraping over Tailscale is sufficient (HTTP polling every 5s)

**Known limitation (S-01):** The `hostmetrics` receiver captures CPU/memory of
the benchmarking host, not the remote engine machine. Accepted for Phase 1.
To be revisited if remote becomes a primary use case.

## Consequences

**Positive:**
- `run_id` namespacing is automatic (in template config, not logic)
- No dynamic discovery or registration
- Sidecar dies cleanly with the run; no lingering scrape targets
- Each sidecar is independent — no cross-run interference
- Scales horizontally

**Negative:**
- One `otelcol-contrib` process per run (~20 MB each)
- Template maintenance (Jinja2 syntax, OTel config changes)
- `hostmetrics` captures benchmarking host for remote runs (S-01)
- Central collector still needed for aggregation and VictoriaMetrics forwarding

## Alternatives Considered

1. **Centralized collector with dynamic scrape targets** — Rejected: operational complexity, lifecycle coupling
2. **Co-located sidecar on engine machine** — Rejected for Phase 1: requires deploying otelcol-contrib on every remote GPU server, violating zero-pre-install contract. Revisit in Phase 2.
3. **Instrumentation SDK in backend only** — Rejected: doesn't capture engine-level metrics (GPU, KV cache, queue depth)

## Related

- Template: `infra/sidecar.yaml.j2`
- Instantiation: `backend/sidecar.py` → `start_sidecar()`
- Spec: `docs/spec/04-otel-sidecar.md`
- Ollama special case: no native `/metrics` → Python shim (`drivers/ollama_shim.py`) on port 9091
- S-01 open item: `docs/review.md`
