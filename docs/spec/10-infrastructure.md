# Inference Benchrunner — Infrastructure Configuration

## docker-compose.yml

```yaml
version: "3.9"

networks:
  bench-net:
    driver: bridge

services:

  backend:
    build: ./backend
    ports: ["8080:8080"]
    environment:
      - DATABASE_URL=sqlite:///./data/bench.db
      - OTEL_COLLECTOR_ENDPOINT=http://otel-collector:4317
      - VICTORIAMETRICS_URL=http://victoriametrics:8428
      - AGENT_URL=http://agent:8787
    volumes:
      - ./data:/app/data
      # docker.sock NOT here — moved to agent service
    depends_on:
      agent:
        condition: service_healthy
      victoriametrics:
        condition: service_healthy
      otel-collector:
        condition: service_healthy
    networks: [bench-net]

  agent:
    build: ./backend              # same image as backend
    command: uvicorn agent:app --host 0.0.0.0 --port 8787
    ports: ["8787:8787"]
    volumes:
      - ./data:/app/data
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
    volumes:
      - ./infra/grafana/provisioning:/etc/grafana/provisioning
      - grafana-data:/var/lib/grafana
    depends_on:
      victoriametrics:
        condition: service_healthy
    networks: [bench-net]

volumes:
  vm-data:
  grafana-data:
```

## Key docker-compose decisions

- **docker.sock on agent, not backend** — agent spawns engines, backend doesn't.
  Reduces backend's privileges. Backend calls agent via http://agent:8787.
- **Agent uses same image as backend** — no extra Dockerfile. Just a different
  uvicorn entrypoint. Engine-specific deps (vllm, sglang, etc.) must be in
  the shared backend/requirements.txt.
- **backend depends_on agent** — agent must be healthy before backend starts.
  Prevents backend from attempting engine operations before agent is ready.

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

service:
  pipelines:
    metrics:
      receivers:  [otlp]
      processors: [batch]
      exporters:  [prometheusremotewrite]
```
