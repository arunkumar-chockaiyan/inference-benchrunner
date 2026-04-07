# InferenceBenchRunner — cross-platform task runner
# Install: winget install Casey.Just | brew install just | cargo install just
# Usage:   just <recipe>       e.g. just up, just test, just migrate

set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

# ── Stack ──────────────────────────────────────────────────────────────────────

# Start full Docker Compose stack (foreground)
up:
    docker compose up

# Start full Docker Compose stack (background)
up-d:
    docker compose up -d

# Stop all services
down:
    docker compose down

# Rebuild all Docker images
build:
    docker compose build

# Tail logs from all services
logs:
    docker compose logs -f

# ── Dev servers (hot-reload) ───────────────────────────────────────────────────

# Start backend dev server on :8080
backend:
    cd backend ; uvicorn main:app --reload --port 8080

# Start agent dev server on :8787
agent:
    cd agent ; uvicorn agent:app --reload --port 8787

# Start frontend dev server on :3000
frontend:
    cd frontend ; npm run dev

# ── Database ───────────────────────────────────────────────────────────────────

# Apply all pending Alembic migrations
migrate:
    docker compose run --rm backend alembic upgrade head

# Generate a new Alembic migration (usage: just migration "add_suite_table")
migration msg:
    docker compose run --rm backend alembic revision --autogenerate -m "{{msg}}"

# Wipe DB volume + recreate schema — use freely while schema is still being refined
db-reset:
    docker compose down -v
    docker compose up -d --wait postgres
    docker compose run --rm backend alembic upgrade head

# DESTRUCTIVE: Wipes DB, deletes all existing migrations, and creates a fresh single initial_schema
# Use this when refining the data model in early dev to avoid dozens of tiny migration files
db-squash:
    docker compose down -v
    docker compose up -d --wait postgres
    docker compose run --rm backend sh -c "rm -f alembic/versions/*.py"
    docker compose run --rm backend alembic revision --autogenerate -m "initial_schema"
    docker compose run --rm backend alembic upgrade head

# Seed engine model registry from data/seed_models.json (backend must be running)
# Usage: just seed-models                        → seed all engines
#        just seed-models --engine ollama        → one engine only
#        just seed-models --dry-run              → preview without writing
seed-models *args:
    python backend/seed_models.py --base-url http://localhost:8080 {{args}}

# ── Testing ────────────────────────────────────────────────────────────────────

# Run all tests (backend + frontend)
test: test-backend test-frontend

# Run backend tests
test-backend:
    cd backend ; pytest -x -v --tb=short --no-header

# Run agent tests
test-agent:
    cd agent ; pytest -x -v --tb=short --no-header

# Run frontend tests
test-frontend:
    cd frontend ; npm test -- --run

# ── Lint / Format ──────────────────────────────────────────────────────────────

# Lint backend + agent Python code
lint:
    cd backend ; ruff check .
    cd agent ; ruff check .

# Format backend + agent Python code
fmt:
    cd backend ; ruff format .
    cd agent ; ruff format .

# Type-check backend Python code
typecheck:
    cd backend ; mypy .

# ── Install ────────────────────────────────────────────────────────────────────

# Install all dependencies (backend + agent + frontend)
install: install-backend install-agent install-frontend

# Install backend Python dependencies
install-backend:
    pip install -r backend/requirements.txt

# Install agent Python dependencies
install-agent:
    pip install -r agent/requirements.txt

# Install frontend npm dependencies
install-frontend:
    cd frontend ; npm install

# ── Frontend build ─────────────────────────────────────────────────────────────

# Production build of frontend (outputs to frontend/dist)
build-frontend:
    cd frontend ; npm run build

# Preview production build locally
preview-frontend:
    cd frontend ; npm run preview
