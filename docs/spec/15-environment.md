# Inference Benchrunner — Environment Variables

## .env.example (create in Phase 1 Step 1)

```bash
# App backend
DATABASE_URL=postgresql+asyncpg://bench:bench@postgres:5432/bench
OTEL_COLLECTOR_ENDPOINT=http://otel-collector:4317
# On Linux host (sidecar outside Docker): use 172.17.0.1:4317 or host.docker.internal:4317
VICTORIAMETRICS_URL=http://victoriametrics:8428
GRAFANA_URL=http://localhost:3001           # browser-facing URL — must be reachable by the user's browser
                                            # change to host IP if accessing from another machine
SECRET_KEY=changeme-replace-with-32-random-bytes          # reserved for future user auth, unused Phase 1

# Agent (local docker-compose; for remote the host comes from RunConfig.host + agent_port)
AGENT_URL=http://agent:8787
AGENT_SECRET_KEY=changeme-replace-with-different-32-bytes # shared key — must match on all agent hosts
CLICKHOUSE_URL=http://clickhouse:8123       # Phase 1 — direct HTTP interface

# Remote via Tailscale
# Remote hosts in RunConfig.host should be Tailscale IPs (100.x.x.x) or MagicDNS (*.ts.net)
# Default agent port: 8787 — override per-run via RunConfig.agent_port

# Ollama shim (injected by backend when spawning shim subprocess — do not set manually)
RUN_ID=
MODEL_NAME=

# Phase 3 (optional — do not set until Phase 3 triggered)
KAFKA_BROKERS=kafka:9092
```

## Notes

- `DATABASE_URL` — PostgreSQL with asyncpg driver from Phase 1. Use `postgresql+asyncpg://` scheme. Never use SQLite.
- `OTEL_COLLECTOR_ENDPOINT` — used by two consumers: (1) each OTel sidecar to forward scraped engine metrics, (2) the backend OTel SDK to push app-level `bench_request_*` metrics. When sidecars run outside Docker on Linux, use the bridge IP or host.docker.internal.
- `VICTORIAMETRICS_URL` — used by the backend for health checks and by the compare endpoint to validate connectivity. Grafana reads VictoriaMetrics directly via its provisioned datasource.
- `GRAFANA_URL` — browser-facing base URL for Grafana deep-links on the run detail page (`{GRAFANA_URL}/d/bench-dashboard/bench?var-run_id=...`). Must be reachable by the user's browser — use `http://localhost:3001` for local dev, or the host IP/hostname for remote access. Never use the Docker-internal address (`grafana:3000`) here.
- `AGENT_URL` — Docker-internal address of the local agent service. Used by the backend for the local docker-compose agent only. Remote agents are addressed via `RunConfig.host:RunConfig.agent_port` at runtime.
- `SECRET_KEY` — reserved for future JWT/session auth. Not used in Phase 1. Must differ from `AGENT_SECRET_KEY`.
- `AGENT_SECRET_KEY` — pre-shared key for backend → agent service-to-service auth. Must be identical on the benchmarking host and every remote agent host. Must differ from `SECRET_KEY`. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
- `CLICKHOUSE_URL` — HTTP interface for `clickhouse-connect`. Used by `ch_insert()` in runner.py for best-effort per-request event writes. Removed in Phase 3 when Kafka consumer takes over.
- `RUN_ID` + `MODEL_NAME` — injected by OllamaDriver when spawning ollama_shim.py subprocess. Do not set manually.
