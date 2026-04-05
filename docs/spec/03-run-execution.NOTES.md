# Run Execution — Implementation Notes

## Step 7 — execute_run() + collect_record() + ch_insert() + start_sidecar() — 2025-04-03

### execute_run() signature
- Deviation: signature is `execute_run(run_id, config, suite, db)` — spec pseudocode omitted `db`.
  A `db: AsyncSession` parameter was added because SQLAlchemy 2.0 async does not support
  context-manager-style session creation inside a running event loop without a workaround.
  The background task (`_run_background`) creates its own `AsyncSessionLocal()` session and
  passes it to `execute_run`.

### Prompt loading
- Deviation: prompts are loaded explicitly inside `execute_run` via
  `select(SuitePrompt).options(joinedload(SuitePrompt.prompt)).order_by(SuitePrompt.position)`
  rather than using `suite.prompts` lazy relationship access. This is required because
  SQLAlchemy async raises `MissingGreenlet` on lazy loads inside `asyncio.gather` tasks.

### collect_record() double-write guard
- Deviation: `collect_record` wraps the `ch_insert` call in an extra `try/except` at the
  call site in addition to `ch_insert`'s own swallow. Belt-and-suspenders — `ch_insert`
  is documented as never raising, but the guard prevents any edge case from surfacing.

### update_run_status() double-write guard
- Deviation: `execute_run`'s outer `except Exception` block skips calling
  `update_run_status("failed")` when the exception is a `RuntimeError("unhealthy")`
  because the watchdog's error handler already set the status. Prevents duplicate writes.

### CancelledError flow
- `asyncio.CancelledError` is caught, status set to "cancelled", then re-raised so the
  `finally` cleanup block still runs. This matches the spec exactly.

## Next session needs to know
- `execute_run` takes `db: AsyncSession` — callers must provide it.
- Background task pattern in `routers/runs.py`: `_run_background(run_id)` creates its own
  session to avoid detached-object errors from route-scoped sessions.
- `_run_tasks: dict[UUID, asyncio.Task]` in `routers/runs.py` — module-level; reset on
  process restart. Recovery of in-flight tasks after restart is handled by `recover_stale_runs()`.
