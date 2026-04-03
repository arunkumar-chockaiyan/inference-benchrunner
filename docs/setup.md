# InferenceBenchRunner — Development Setup

## Prerequisites

### Required

| Tool | Version | Install |
|------|---------|---------|
| **Docker Desktop** | v4+ (Compose v2) | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Python** | 3.13+ | [python.org/downloads](https://www.python.org/downloads/) |
| **Node.js** | 22 LTS+ | [nodejs.org](https://nodejs.org/) |
| **Git** | any | [git-scm.com](https://git-scm.com/) |
| **otelcol-contrib** | latest | See [OTel Collector setup](#otel-collector-contrib) below |

### Optional (for specific workflows)

| Tool | Version | When needed |
|------|---------|-------------|
| **Tailscale** | latest | Remote machine benchmarking |
| **just** | latest | Full task runner (`just up`, `just test`, `just migrate`, etc.) — install via `winget install Casey.Just` |
| **Ollama** | latest | Local inference testing with Ollama engine |
| **llama-server** | latest | Local inference testing with llama.cpp |
| **vLLM** | latest | GPU inference testing (requires CUDA) |
| **SGLang** | latest | GPU inference testing (requires CUDA) |

---

## 1. Clone and configure

```bash
git clone <repo-url>
cd InferenceBenchRunner
cp .env.example .env
```

Edit `.env` and generate real secrets:

```bash
# Generate AGENT_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Generate SECRET_KEY (must differ from AGENT_SECRET_KEY)
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated values into `.env`.

---

## 2. Install backend dependencies

```bash
pip install -r backend/requirements.txt
```

For development tools (linting, type checking):

```bash
pip install ruff mypy
```

---

## 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

Frontend stack: React 19, TypeScript, Vite 8 (Rolldown), Zustand, Recharts, Tailwind CSS v4.

---

## 4. Start infrastructure

```bash
docker compose up -d
```

This starts: PostgreSQL, ClickHouse, VictoriaMetrics, OTel Collector, Grafana, Agent.

Wait for all services to be healthy:

```bash
docker compose ps
```

---

## 5. Run database migrations

```bash
cd backend && alembic upgrade head
```

---

## 6. Run dev servers

In separate terminals:

```bash
# Terminal 1 — Backend
just backend
# or: cd backend && uvicorn main:app --reload --port 8080

# Terminal 2 — Frontend
npm run dev
# or: just frontend
```

Access points:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8080
- **Grafana**: http://localhost:3001 (admin/admin)
- **VictoriaMetrics**: http://localhost:8428

---

## OTel Collector Contrib

The backend spawns `otelcol-contrib` as a sidecar subprocess for each benchmark
run. This binary must be available on the system PATH of the machine running
the backend (the benchmarking host).

> **Note:** This is the *sidecar* collector binary, separate from the central
> OTel Collector that runs inside Docker Compose. The central collector receives
> data from sidecars — the sidecar runs on the host outside Docker.

### Windows

1. Download the latest release from:
   https://github.com/open-telemetry/opentelemetry-collector-releases/releases

2. Look for `otelcol-contrib_<version>_windows_amd64.tar.gz` under Assets.

3. Extract and place `otelcol-contrib.exe` in a directory on your PATH, e.g.:

   ```powershell
   # Create directory
   mkdir "C:\Tools\otelcol"

   # Extract the downloaded archive to that directory
   # (use tar, 7-Zip, or similar)

   # Add to PATH (current user, persistent)
   [Environment]::SetEnvironmentVariable(
       "Path",
       $env:Path + ";C:\Tools\otelcol",
       [EnvironmentVariableTarget]::User
   )
   ```

4. Verify:

   ```powershell
   otelcol-contrib --version
   ```

### macOS

```bash
brew install open-telemetry/opentelemetry-collector/opentelemetry-collector-contrib
```

Or download the binary from the GitHub releases page (look for `darwin_arm64` or `darwin_amd64`).

### Linux

```bash
# Download latest release
OTEL_VERSION=$(curl -s https://api.github.com/repos/open-telemetry/opentelemetry-collector-releases/releases/latest | grep tag_name | cut -d '"' -f 4 | sed 's/^v//')
curl -LO "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${OTEL_VERSION}/otelcol-contrib_${OTEL_VERSION}_linux_amd64.tar.gz"

# Extract and install
tar xzf otelcol-contrib_${OTEL_VERSION}_linux_amd64.tar.gz
sudo mv otelcol-contrib /usr/local/bin/
otelcol-contrib --version
```

### Sidecar ↔ Docker connectivity

The sidecar runs on the host and needs to reach the central OTel Collector
inside Docker:

| OS | OTEL_COLLECTOR_ENDPOINT value |
|----|-------------------------------|
| **macOS / Windows** | `http://host.docker.internal:4317` |
| **Linux** | `http://172.17.0.1:4317` (Docker bridge IP) |

Set this in your `.env` file when running the backend outside Docker.

---

## Testing

```bash
# Backend tests
just test-backend
# or: cd backend && pytest -x -v --tb=short --no-header

# Frontend tests
npm test
# or: just test-frontend

# Agent tests
just test-agent

# Lint
just lint

# Type check
just typecheck
```

### Test database

Backend tests use a separate `bench_test` database. Create it before running tests:

```sql
-- Connect to PostgreSQL
CREATE DATABASE bench_test;
```

Or via CLI:

```bash
docker compose exec postgres createdb -U bench bench_test
```

---

## Troubleshooting

### "otelcol-contrib: command not found"

The sidecar binary isn't on PATH. Follow the [OTel Collector setup](#otel-collector-contrib)
section above.

### Backend can't connect to PostgreSQL

Ensure Docker Compose is running (`docker compose ps`). For local dev outside
Docker, `DATABASE_URL` in `.env` should use `localhost:5432` (not `postgres:5432`).

### Sidecar can't reach central collector

Set `OTEL_COLLECTOR_ENDPOINT` to the correct host-to-Docker address for your
OS. See the [Sidecar ↔ Docker connectivity](#sidecar--docker-connectivity) table.

### Grafana deep-link shows wrong URL

`GRAFANA_URL` in `.env` must be a browser-facing address (`http://localhost:3001`),
not the Docker-internal address (`http://grafana:3000`).
