# QA Spec — Data Models & Database

Source: `docs/spec/01-data-models.md`, `backend/models.py`, `backend/database.py`

---

## Test areas

### 1. SQLAlchemy model instantiation

Verify every model can be constructed with valid fields and persisted.

| Model | Key assertions |
|-------|---------------|
| `Prompt` | `content` allows `{{variable}}` syntax; `variables` is a dict JSON column |
| `PromptSuite` | `version` starts at 1, auto-increments on update via `before_update` event listener |
| `SuitePrompt` | `position` enforces order; FK constraints to `suite_id` and `prompt_id` hold |
| `RunConfig` | `spawn_mode` only accepts `"managed"` or `"attach"` |
| `Run` | `Run.id` is the run_id — UUID set at creation, used as the spine across all OTel metrics; `status` starts as `"pending"` |
| `RequestRecord` | `attempt` is 1-based; `status` in `{"success","error","timeout"}` |
| `EngineModel` | composite unique on `(engine, host, model_id)` enforced at DB level |
| `SavedComparison` | `share_token` unique; `run_ids` stored as JSON list |

### 2. Run status transitions

Valid FSM:
```
pending → starting → warming_up → running → completed
                                          → failed
                                          → cancelled
```

Test cases:
- Transition `pending → starting` sets `started_at`
- Transition `running → completed` sets `completed_at`
- Transition to `failed` populates `error_message`
- Note: FSM transitions are enforced at the application layer (`execute_run()`), not at the DB level — `Run.status` is a plain string column

### 3. run_id immutability

- `Run.id` is the run_id — the UUID primary key stamped on every OTel metric, RequestRecord, and ClickHouse event row
- All associated `RequestRecord` rows carry a `run_id` FK equal to `Run.id`
- Immutability is an application-layer invariant (set once at run creation, never reassigned); there is no separate DB constraint beyond the primary key

### 4. Async session — no sync leaks

- All DB fixture operations use `async with AsyncSession(...)`
- Assert no `Session` (sync) objects are created in any test helper

### 5. Alembic migrations

- `alembic upgrade head` applies cleanly against a fresh PostgreSQL DB
- `alembic downgrade -1` then `upgrade head` leaves schema identical
- Running `alembic revision --autogenerate` against current models produces an empty migration (no drift)

### 6. JSON columns

| Column | Test |
|--------|------|
| `Prompt.variables` | Empty dict `{}` round-trips; nested strings preserved |
| `RunConfig.variable_overrides` | `None` is valid; dict values override prompt defaults |
| `RunConfig.tags` | Empty list `[]` valid; list of strings preserved |
| `Run.config_snapshot` | Full dict captured at run start; survives config mutation |
| `SavedComparison.run_ids` | List of UUID strings stored and retrieved as list |

### 7. EngineModel sync behaviour

- `source="synced"` record: update `last_synced` and clear `is_stale` on re-sync
- `source="synced"` record absent from most recent sync: set `is_stale=True`, do NOT delete
- `source="manual"` record: never overwritten by sync; `is_stale` always `False`
- Unique constraint `(engine, host, model_id)`: insert duplicate raises `IntegrityError`
- `llamacpp` models: always `source="manual"`, sync is no-op (returns `[]`)

### 8. SpawnResult + Run process tracking

- `Run.server_owned = True` when `SpawnResult.owned = True`
- `Run.server_pid` set from `SpawnResult.pid`
- `Run.sidecar_pid` set after `start_sidecar()` returns
- `Run.cleanup_warning` set if teardown agent is unreachable

### 9. PostgreSQL-specific types

- `UUID` columns use PostgreSQL native UUID type — Python `uuid.UUID` objects after round-trip
- JSON columns use `sa.JSON()` (not JSONB) — ClickHouse-compatible; key-level indexing not required
- `DateTime(timezone=True)` maps to `TIMESTAMPTZ` — all datetime values are timezone-aware after round-trip

---

## Fixtures

Defined in `backend/tests/conftest.py`:

```python
# Session-scoped engine — creates all tables once, drops at end of session
@pytest_asyncio.fixture(scope="session")
async def engine():
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()

# Function-scoped session — rolls back after each test
@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
```

`pyproject.toml` sets `asyncio_default_fixture_loop_scope = "session"` so the session-scoped
`engine` fixture and function-scoped `db` fixture share the same event loop.

Use `db` (not `db_session`) in all tests. Use `engine` (not `pg_engine`) in fixtures that need
direct engine access.
