# ADR-0003: OTel Sidecar Per Run (Not Centralized)

**Date:** 2026-03-31
**Status:** Accepted
**Context:** InferenceBenchRunner spawns short-lived inference engines for each run and must collect per-engine metrics (CPU, memory, throughput, latency).

## Problem

If a single central OTel collector scrapes all running engines:
- Collector becomes a bottleneck
- Difficult to namespace metrics by `run_id` without a registration mechanism
- Hard to clean up metrics when a run ends (lingering scrape targets)
- Tight coupling between collector config and active runs
- Requires dynamic scrape target discovery (complex)

## Decision

**Each run spawns its own OTel sidecar** (a separate `otelcol-contrib` process) from a Jinja2 template (`sidecar.yaml.j2`):

1. User starts a run
2. `execute_run()` instantiates the Jinja2 template with `run_id`, engine metrics port, etc.
3. Template → concrete `otelcol-config-{run_id}.yaml`
4. `start_sidecar()` spawns `otelcol-contrib --config=...` as a subprocess
5. Sidecar:
   - Scrapes engine's `/metrics` endpoint (e.g., `:8000/metrics` for vLLM)
   - Stamps `run_id`, `model`, `engine` labels on every metric
   - Buffers to disk
   - Forwards to central OTel Collector
6. On run cleanup: `teardown()` kills the sidecar process

## Consequences

**Positive:**
- Namespacing metrics by `run_id` is automatic (in config, not logic)
- No dynamic discovery or registration logic
- Sidecar dies cleanly with the run
- Each sidecar is independent; no cross-run interference
- Scales horizontally (one sidecar per run)

**Negative:**
- One process per run (small footprint ~20 MB/sidecar)
- Template maintenance (Jinja2 syntax, updates to OTel config)
- Debugging requires looking at per-run sidecar logs
- Central collector still needed for aggregation

## Alternatives Considered

1. **Centralized collector with dynamic scrape targets** — Rejected because operational complexity
2. **Agent mode (Prometheus-style push)** — Rejected because engines expose pull-only metrics
3. **Instrumentation SDK in backend** — Rejected because doesn't capture engine-level metrics (CPU, memory)

## Related

- Template: `infra/sidecar.yaml.j2`
- Instantiation: `backend/orchestration.py:start_sidecar()`
- Ollama special case: no native `/metrics` → Python shim (`ollama_shim.py`) on port 9091
