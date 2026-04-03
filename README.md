# InferenceBenchRunner

Benchmarking tool for LLM inference engines. Configure runs (engine + model + prompt suite + parameters), fire them at local or remote inference servers, collect per-request metrics via an OTel sidecar, and compare results across runs in Grafana.

**Supported engines:** Ollama, llama.cpp server, vLLM, SGLang

---

## Quick Start

> **First time?** See [`docs/setup.md`](docs/setup.md) for full prerequisites
> (Python 3.13+, Node 22+, Docker, otelcol-contrib) and step-by-step setup.

```bash
# Copy environment template
cp .env.example .env
# Edit .env — set SECRET_KEY, AGENT_SECRET_KEY, and DATABASE_URL

# Start full stack
docker compose up

# Open Grafana
open http://localhost:3001

# Open frontend
open http://localhost:3000
```

---

## Development

Common tasks via **npm** (zero install) or [**just**](https://github.com/casey/just) (full command set):

```bash
# Frontend dev server
npm run dev              # or: just frontend

# Run frontend tests
npm test                 # or: just test

# Start Docker stack
npm run up               # or: just up

# Production build
npm run build            # or: just build-frontend
```

Full command set via `just` (install: `winget install Casey.Just`):

```bash
just backend             # Backend dev server (hot-reload, :8080)
just agent               # Agent dev server (hot-reload, :8787)
just migrate             # Apply Alembic migrations
just migration "msg"     # Generate new migration
just lint                # Lint backend + agent (ruff)
just fmt                 # Format backend + agent (ruff)
just typecheck           # Type-check backend (mypy)
just install             # Install all dependencies
```

---

## Architecture

```
frontend (React/Vite :3000)
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

## Docs

See `docs/spec/` for full design documentation. Start with:
- [`docs/setup.md`](docs/setup.md) — **development setup, prerequisites, and install guide**
- `docs/spec/00-overview.md` — project context and design decisions
- `docs/spec/11-build-order.md` — build phases and current progress
- `docs/adr/` — architecture decision records
