# Stage 1: build — compile wheels that need gcc/libpq-dev
FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime — no build tools, non-root user
FROM python:3.13-slim

WORKDIR /app

# libpq5: asyncpg runtime dep; wget: healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd -r -u 1001 -g root appuser

COPY . .

RUN chown -R appuser:root /app && chmod -R g=u /app

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port 8080"]
