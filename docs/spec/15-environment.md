# Inference Benchrunner — Environment Variables

## .env.example (create in Phase 1 Step 1)

```bash
# App backend
DATABASE_URL=sqlite:///./data/bench.db
OTEL_COLLECTOR_ENDPOINT=http://otel-collector:4317
# On Linux host (sidecar outside Docker): use 172.17.0.1:4317 or host.docker.internal:4317
VICTORIAMETRICS_URL=http://victoriametrics:8428
GRAFANA_URL=http://grafana:3001
SECRET_KEY=changeme-random-32-bytes         # reserved for future auth, unused Phase 1

# Remote via Tailscale
TAILSCALE_ENABLED=true
# Remote hosts should be Tailscale IPs (100.x.x.x) or MagicDNS names
# Default agent port: 8787 — override per-run via RunConfig.agent_port

# Ollama shim (set by backend when spawning shim subprocess — do not set manually)
RUN_ID=
MODEL_NAME=

# Phase 3 (optional — do not set until Phase 3 triggered)
KAFKA_BROKERS=kafka:9092
CLICKHOUSE_URL=http://clickhouse:8123
```

## Notes

- `SECRET_KEY` — reserved for future JWT/session auth. Not used in Phase 1.
- `RUN_ID` + `MODEL_NAME` — injected by OllamaDriver when spawning ollama_shim.py subprocess. Do not set manually.
- `OTEL_COLLECTOR_ENDPOINT` — used by both the backend (to push app-level metrics) and by each OTel sidecar (to forward scraped engine metrics). When sidecars run outside Docker on Linux, use the bridge IP or host.docker.internal.
- `TAILSCALE_ENABLED` — informational flag. Remote hosts in RunConfig.host should be Tailscale IPs or MagicDNS names when Tailscale is in use.

## Additional variable

```bash
# Agent (set in backend environment)
AGENT_URL=http://agent:8787   # local docker-compose agent
                               # for remote: set per-run via RunConfig.host + agent_port
```
