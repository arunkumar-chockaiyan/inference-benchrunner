# API Routes — Implementation Notes

## Step 8+9 — FastAPI routes + WebSocket — 2025-04-03

### POST /api/runs — inline RunConfig creation
- Deviation: spec did not specify a separate `POST /api/run-configs` endpoint.
  `POST /api/runs` creates both a `RunConfig` and a `Run` atomically in one request.
  This matches the wizard flow (all parameters entered in one wizard session → single API call).
  RunConfig can be re-used by reading `run.config` from `RunRead`, but there is no endpoint
  to create a RunConfig without immediately starting a run in Phase 1.

### WebSocket router separation
- Deviation: `ws_router` is a separate `APIRouter()` (no prefix) exported alongside `router`
  from `routers/runs.py`. `main.py` includes both routers. This avoids the WebSocket endpoint
  being prefixed with `/api/runs` (it lives at `/ws/runs/{id}` not `/api/runs/ws/{id}`).

### Schemas — RunSummary flattened fields
- Deviation: `RunSummary` includes `engine`, `model`, `host` from `RunConfig` (not from `Run`).
  These are populated in the list route by joining `Run` with `RunConfig` and constructing
  `RunSummary` objects manually with `RunSummary(...)` rather than `model_validate(run)`.
  The `model_config = {"from_attributes": True}` on `RunSummary` is not used for list queries.

### Compare endpoint — Python percentile computation
- Deviation: percentile stats (p50, p99) are computed in Python using a sorted-list index
  approach rather than PostgreSQL's `percentile_cont()`. This is simpler for Phase 1 and
  avoids raw SQL in the router. Performance is acceptable for Phase 1 run sizes.

### POST /api/runs/compare route registration
- Route is registered BEFORE `GET /api/runs/{id}` as required by the spec.
  FastAPI matches literal path segments before parameterized ones only when routes are
  registered in that order — this is enforced by the order of decorators in runs.py.

## Next session needs to know
- `POST /api/runs` creates `RunConfig` + `Run` — no separate RunConfig CRUD in Phase 1.
- `ws_router` must always be included separately from `router` in `main.py`.
- Stats computation is Python-side — if perf becomes an issue in Phase 2, migrate to
  `percentile_cont()` SQL aggregation.
