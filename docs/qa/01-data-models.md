# QA Spec — Data Models & Database

Source: `docs/spec/01-data-models.md`, `backend/models.py`, `backend/database.py`

---

## Test areas

### 1. SQLAlchemy model instantiation

Verify every model can be constructed with valid fields and persisted.

| Model | Key assertions |
|-------|---------------|
| `Prompt` | `content` allows `{{variable}}` syntax; `variables` is a dict JSON column |
| `PromptSuite` | `version` starts at 1, auto-increments on update |
| `SuitePrompt` | `position` enforces order; FK constraints to `suite_id` and `prompt_id` hold |
| `RunConfig` | `spawn_mode` only accepts `"managed"` or `"attach"` |
| `Run` | `run_id` UUID set once, immutable; `status` starts as `"pending"` |
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
- Direct jump from `pending → completed` must not occur (invariant test)
- No transition out of terminal states (`completed`, `failed`, `cancelled`)

### 3. run_id immutability

- Create `Run` with a UUID `run_id`
- Attempt to update `run_id` → assert DB constraint or application guard prevents it
- All associated `RequestRecord` rows share the same `run_id`

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
| `Run.config_snapshot` | Full `RunConfig` dict captured at run start; survives config mutation |
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

- `UUID` columns use PostgreSQL native UUID (not VARCHAR)
- `JSONB` columns (where applicable) support key-level queries
- `timestamptz` columns store timezone-aware datetimes

---

## Fixtures

```python
@pytest.fixture
async def db_session(pg_engine):
    async with AsyncSession(pg_engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
def basic_prompt(db_session):
    return Prompt(
        id=uuid4(), name="test", content="Hello {{name}}",
        category="short", variables={"name": "world"},
    )
```
