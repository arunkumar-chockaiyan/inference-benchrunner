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
  - `docker-compose.yml` (Step 11) must include a `postgres:16` service — see approved plan at `C:\Users\Arun\.claude\plans\wise-sparking-patterson.md`.
  - Run `cd backend && alembic upgrade head` to apply schema after `docker compose up postgres`.
  - Test DB fixture in `backend/tests/conftest.py` targets `bench_test` database — create it manually or via CI before running tests.
