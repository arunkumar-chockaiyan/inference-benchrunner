.PHONY: up down build logs backend frontend agent test test-backend test-frontend migrate lint fmt

# ── Stack ──────────────────────────────────────────────────────────────────────

up:
	docker compose up

up-d:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

# ── Dev servers (hot-reload) ───────────────────────────────────────────────────

backend:
	cd backend && uvicorn main:app --reload --port 8080

agent:
	cd agent && uvicorn agent:app --reload --port 8787

frontend:
	cd frontend && npm run dev

# ── Database ───────────────────────────────────────────────────────────────────

migrate:
	cd backend && alembic upgrade head

migration:
	cd backend && alembic revision --autogenerate -m "$(msg)"

# ── Testing ────────────────────────────────────────────────────────────────────

test: test-backend test-frontend

test-backend:
	cd backend && pytest -x -v --tb=short --no-header

test-agent:
	cd agent && pytest -x -v --tb=short --no-header

test-frontend:
	cd frontend && npm test -- --run

# ── Lint / Format ──────────────────────────────────────────────────────────────

lint:
	cd backend && ruff check .
	cd agent && ruff check .

fmt:
	cd backend && ruff format .
	cd agent && ruff format .

typecheck:
	cd backend && mypy .

# ── Install ────────────────────────────────────────────────────────────────────

install-backend:
	pip install -r backend/requirements.txt

install-agent:
	pip install -r agent/requirements.txt

install-frontend:
	cd frontend && npm install
