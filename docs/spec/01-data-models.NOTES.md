# Data Models — Deviation Notes

## Step 1 — Database models + SQLAlchemy async setup + Alembic init — 2026-04-01

- Deviation: PostgreSQL (`asyncpg`) used from Phase 1 instead of SQLite per user instruction.
  `DATABASE_URL=postgresql+asyncpg://bench:bench@localhost:5432/bench`

- Column type choices (PostgreSQL-native from day 1):
  - All `id` and UUID FK columns: `UUID(as_uuid=True)` — native PostgreSQL UUID type
  - All JSON columns (`variables`, `config_snapshot`, `tags`, `variable_overrides`, `run_ids`): `sqlalchemy.JSON` — PostgreSQL resolves to JSONB
  - All datetime columns: `DateTime(timezone=True)` — stores as `TIMESTAMP WITH TIME ZONE`

- `aiosqlite` is NOT a dependency — do not add it.
- `asyncpg>=0.29` is the async DB driver.
- `backend/config.py` added (not in spec) — pydantic-settings `Settings` class that reads `.env`. Imported by `database.py` and (later) `main.py`.
- Alembic `env.py` uses `run_async_migrations()` with `asyncio.run()` — required for `asyncpg` async driver.

- Next session needs to know:
  - Phase 2 Step 22 (PostgreSQL migration) is marked N/A — already done.
  - `docker-compose.yml` (Step 11) must include a `postgres:17` service (spec updated from :16).
  - Run `cd backend && alembic upgrade head` to apply schema after `docker compose up postgres`.
  - Test DB fixture in `backend/tests/conftest.py` targets `bench_test` database — create it manually or via CI before running tests.

## Pre-Phase-1 review — EngineModel.is_stale added — 2026-04-03

- `is_stale: bool` added to `EngineModel` model (was missing despite being in the spec after R-18 fix).
- **Alembic migration required** before running any sync endpoint tests — generate with:
  `alembic revision --autogenerate -m "add_engine_model_is_stale"` then `alembic upgrade head`.

## EngineModel: host removed from registry — 2025-04-06

- Deviation: `host` column dropped from `engine_models` table. Spec included `host` in the
  unique key `(engine, host, model_id)` and showed a Host column in the model registry UI.
- Reason: Tying a model to a specific host prevents reuse. A registered model (e.g.
  `ollama/llama3.1:8b`) should be selectable against any host — localhost or remote — when
  creating a run config. Host is a runtime concern that belongs in RunConfig, not the registry.
- New unique constraint: `(engine, model_id)` — `uq_engine_model`.
- Sync endpoint still accepts `host` + `port` as ephemeral query params to reach the live
  engine for discovery, but does not store them.
- Stale logic now scoped per-engine only (not per engine+host).
- Migration: `backend/alembic/versions/20250406_0002_remove_host_from_engine_models.py`
- Affected files: models.py, schemas/engine.py, routers/engines.py, api/index.ts,
  ModelRegistry.tsx, seed_models.json, seed_models.py
- Next session needs to know: EngineModel has no host. The wizard engine step must NOT
  filter `listEngineModels` by host — it fetches all models for the engine from the DB registry.
