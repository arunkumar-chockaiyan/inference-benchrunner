# InferenceBenchRunner

Benchmarking tool for LLM inference engines. Configure runs (engine + model + prompt suite + parameters), fire them at local or remote inference servers, collect per-request metrics via an OTel sidecar, and compare results across runs in Grafana.

**Supported engines:** Ollama, llama.cpp server, vLLM, SGLang

---

## Quick Start

```bash
# Copy environment template
cp .env.example .env
# Edit .env — set SECRET_KEY, AGENT_SECRET_KEY, and DATABASE_URL

# Start full stack
docker compose up

# Open Grafana
open http://localhost:3001

# Open frontend
open http://localhost:5173
```

---

## Development

```bash
# Backend dev server (hot-reload)
make backend

# Agent dev server (hot-reload)
make agent

# Frontend dev server
make frontend

# Run all tests
make test

# Database migration
make migrate

# Generate new migration
make migration msg="add_suite_table"
```

---

## Architecture

```
frontend (React/Vite :5173)
    │
backend (FastAPI :8080)
    ├── drivers/          engine ABC + per-engine implementations
    ├── services/         runner, collector, clickhouse, sidecar
    ├── routers/          FastAPI route modules
    └── schemas/          Pydantic request/response models

agent (FastAPI :8787)     engine lifecycle on local and remote hosts

infra/
    sidecar.yaml.j2       OTel sidecar config template (per run)
    otel-collector.yaml   central OTel Collector config
    grafana/              dashboard + datasource provisioning
    clickhouse/init.sql   ClickHouse schema
```

**Storage:**
- PostgreSQL — run configs, prompts, suites, request records
- VictoriaMetrics — engine metrics scraped by per-run OTel sidecar
- ClickHouse — per-request event rows for analytical drill-down

**Remote engines:** Tailscale for network access; FastAPI agent manages engine lifecycle via HTTP. No SSH.

---

## Spec

See `docs/spec/` for full design documentation. Start with:
- `docs/spec/00-overview.md` — project context and design decisions
- `docs/spec/11-build-order.md` — build phases and current progress
- `docs/adr/` — architecture decision records
