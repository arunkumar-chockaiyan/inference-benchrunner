# Inference Benchrunner — Infrastructure Configuration

## docker-compose.yml

```yaml
version: "3.9"

networks:
  bench-net:
    driver: bridge

services:

  postgres:
    image: postgres:17
    environment:
      - POSTGRES_USER=bench
      - POSTGRES_PASSWORD=bench
      - POSTGRES_DB=bench
    ports: ["5432:5432"]
    volumes:
      - pg-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bench"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks: [bench-net]

  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"   # HTTP interface
      - "9000:9000"   # native protocol
    volumes:
      - ch-data:/var/lib/clickhouse
      - ./infra/clickhouse/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8123/ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks: [bench-net]

  backend:
    build: ./backend
    ports: ["8080:8080"]
    environment:
      - DATABASE_URL=postgresql+asyncpg://bench:bench@postgres:5432/bench
      - OTEL_COLLECTOR_ENDPOINT=http://otel-collector:4317
      - VICTORIAMETRICS_URL=http://victoriametrics:8428
      - AGENT_URL=http://agent:8787
      - AGENT_SECRET_KEY=${AGENT_SECRET_KEY}
      - CLICKHOUSE_URL=http://clickhouse:8123
      - GRAFANA_URL=http://localhost:3001    # browser-facing — used for deep-link generation
    depends_on:
      postgres:
        condition: service_healthy
      clickhouse:
        condition: service_healthy
      agent:
        condition: service_healthy
      victoriametrics:
        condition: service_healthy
      otel-collector:
        condition: service_healthy
    networks: [bench-net]

  agent:
    build: ./agent                # separate image — minimal deps (fastapi, uvicorn, httpx)
    command: uvicorn agent:app --host 0.0.0.0 --port 8787
    ports: ["8787:8787"]
    environment:
      - AGENT_SECRET_KEY=${AGENT_SECRET_KEY}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # agent spawns engines
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8787/health"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks: [bench-net]

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - VITE_API_URL=http://localhost:8080
    networks: [bench-net]
    # Phase 1: Vite dev server (acceptable for 2-10 users)
    # Phase 2: replace with nginx serving built static files

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    volumes:
      - ./infra/otel-collector.yaml:/etc/otelcol-contrib/config.yaml
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
    depends_on:
      victoriametrics:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:13133/"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks: [bench-net]

  victoriametrics:
    image: victoriametrics/victoria-metrics:latest
    ports: ["8428:8428"]
    volumes:
      - vm-data:/storage
    command:
      - "--retentionPeriod=12"
      - "--storageDataPath=/storage"
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8428/health"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks: [bench-net]

  grafana:
    image: grafana/grafana:latest
    ports: ["3001:3000"]
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
      - GF_INSTALL_PLUGINS=grafana-clickhouse-datasource
    volumes:
      - ./infra/grafana/provisioning:/etc/grafana/provisioning
      - grafana-data:/var/lib/grafana
    depends_on:
      victoriametrics:
        condition: service_healthy
      clickhouse:
        condition: service_healthy
    networks: [bench-net]

volumes:
  pg-data:
  ch-data:
  vm-data:
  grafana-data:
```

## Key docker-compose decisions

- **docker.sock on agent, not backend** — agent spawns engines, backend doesn't.
  Reduces backend's privileges. Backend calls agent via http://agent:8787.
- **Agent has its own directory and image** (`agent/`) — separate Dockerfile with
  minimal dependencies (fastapi, uvicorn, httpx only). Keeps the remote deployment
  footprint small and separates agent concerns from backend concerns.
- **backend depends_on agent** — agent must be healthy before backend starts.
  Prevents backend from attempting engine operations before agent is ready.
- **AGENT_SECRET_KEY via `${AGENT_SECRET_KEY}`** — read from `.env` at compose
  time; same value injected into both backend and agent services.
- **ClickHouse init.sql** — schema created automatically on first container start
  via the `/docker-entrypoint-initdb.d/` mount. Idempotent (`CREATE TABLE IF NOT EXISTS`).

## Sidecar → collector connectivity

OTel sidecars run on the host (outside Docker). To reach otel-collector:
- macOS / Windows: use `host.docker.internal:4317`
- Linux: use the Docker bridge IP (typically 172.17.0.1:4317)

Set OTEL_COLLECTOR_ENDPOINT accordingly in .env when running outside Docker.

## Central OTel Collector config (infra/otel-collector.yaml)

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s

exporters:
  prometheusremotewrite:
    endpoint: http://victoriametrics:8428/api/v1/write
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s   # buffer up to 5 min of VictoriaMetrics unavailability
    sending_queue:
      enabled: true
      queue_size: 1000

service:
  pipelines:
    metrics:
      receivers:  [otlp]
      processors: [batch]
      exporters:  [prometheusremotewrite]
```
