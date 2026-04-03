# QA Spec — API Routes

Source: `docs/spec/06-api-routes.md`, `backend/routers/`, `backend/main.py`

Use FastAPI `TestClient` (sync) or `httpx.AsyncClient` with `ASGITransport` for all tests.

---

## Route registration order (critical)

FastAPI matches literal segments before path parameters ONLY when registered first.

| Route pair | Registration order required |
|------------|----------------------------|
| `POST /api/prompts/import` | BEFORE `GET /api/prompts/{id}` |
| `GET /api/prompts/export` | BEFORE `GET /api/prompts/{id}` |
| `POST /api/runs/compare` | BEFORE `GET /api/runs/{id}` |

Tests:
- `GET /api/prompts/export` with `Accept: application/json` → `200`, not `404` (not matched as `id="export"`)
- `POST /api/runs/compare` with valid body → `200`, not `422` (not matched as `id="compare"`)

---

## Prompts (`test_prompts.py`)

### CRUD

| Route | Scenario | Expected |
|-------|----------|---------|
| `POST /api/prompts` | Valid prompt | `201` with created prompt |
| `GET /api/prompts/{id}` | Exists | `200` |
| `GET /api/prompts/{id}` | Not found | `404 {"detail": str}` |
| `PUT /api/prompts/{id}` | Valid update | `200` |
| `DELETE /api/prompts/{id}` | Exists | `204` or `200` |

### Pagination

- `GET /api/prompts?limit=5` → returns ≤5 prompts, includes `cursor` in response
- `GET /api/prompts?cursor=<id>&limit=5` → returns next page starting after cursor
- Filter: `?category=code` → only prompts with `category="code"`

### Import / Export

| Route | Input | Expected |
|-------|-------|---------|
| `POST /api/prompts/import` | Valid JSON | Prompts created, count returned |
| `POST /api/prompts/import` | Invalid JSON | `422` |
| `GET /api/prompts/export` | — | JSON array of all prompts |

---

## Suites (`test_prompts.py`)

| Route | Scenario | Expected |
|-------|----------|---------|
| `POST /api/suites` | Valid | `201` |
| `GET /api/suites/{id}` | With prompts | Prompts returned in `position` order |
| `PUT /api/suites/{id}` | Any update | `version` auto-incremented |
| `DELETE /api/suites/{id}` | — | `204` |

---

## Engines (`test_engines.py`)

### List engines

`GET /api/engines` → array of 4 engines with metadata.
Assert `["ollama", "llamacpp", "vllm", "sglang"]` all present.

### Model registry

| Route | Scenario | Expected |
|-------|----------|---------|
| `GET /api/engines/{engine}/models` | Models exist | `200` list |
| `GET /api/engines/{engine}/models?host=...` | Filter by host | Filtered list |
| `POST /api/engines/{engine}/models` | Manual add | `201`, `source="manual"` |
| `DELETE /api/engines/{engine}/models/{id}` | Exists | `204` |

### Sync (`POST /api/engines/{engine}/models/sync`)

| Scenario | Expected |
|----------|---------|
| Engine reachable, returns models | `200`, models upserted to registry |
| Engine `llamacpp` | `200`, no-op (returns `[]`) |
| Engine unreachable | `502` or error response |

Assert: synced models have `source="synced"`, `last_synced` updated.
Assert: manual models (`source="manual"`) are NOT overwritten by sync.
Assert: models absent from sync are marked `is_stale=True`, not deleted.

### Probe

`POST /api/engines/probe` with `{"host": "localhost", "port": 8080, "engine": "llamacpp"}`
- Reachable: `{"reachable": true, "latency_ms": float, "error": null}`
- Unreachable: `{"reachable": false, "latency_ms": null, "error": str}`

---

## Runs (`test_runs.py`)

### Create + start

`POST /api/runs` with valid `RunConfig`:
- Calls `validate_config()` before spawning
- Returns `201` with run `id` and `status="pending"` or `"starting"`

`POST /api/runs` with invalid config:
- Returns `422` with list of validation errors
- No engine spawned

### Run lifecycle via API

| Route | Scenario | Expected |
|-------|----------|---------|
| `GET /api/runs/{id}` | Run exists | `200` with all fields |
| `GET /api/runs/{id}` | Not found | `404` |
| `DELETE /api/runs/{id}` | Run in `"running"` | `200`, run transitions to `"cancelled"` |
| `DELETE /api/runs/{id}` | Run already `"completed"` | `409` (terminal state) |
| `DELETE /api/runs/{id}` | Run already `"failed"` | `409` |

### Run list filters

- `?status=completed` → only completed runs
- `?engine=vllm` → only vllm runs
- `?tag=gpu-test` → runs with that tag
- `?project={id}` → runs in that project
- Pagination: `?cursor&limit`

### Compare

`POST /api/runs/compare`:
```json
{"run_ids": ["uuid1", "uuid2"], "metric": "p99"}
```
Response:
```json
{
  "runs": [
    {"run_id": "uuid1", "avg": float, "p99": float, "min": float,
     "max": float, "stddev": float, "sample_count": int},
    ...
  ]
}
```
Test: `metric` values `"p99"`, `"ttft"`, `"throughput"` all accepted.
Test: unknown `metric` value → `422`.
Test: run with zero `RequestRecord`s → `sample_count=0`, other fields 0 or null.

### Request records

`GET /api/runs/{id}/requests`:
- Returns paginated `RequestRecord` list
- Cursor pagination works correctly
- Only records for this `run_id` returned

---

## Comparisons (`test_comparisons.py`)

### Save comparison

`POST /api/comparisons`:
```json
{"name": "GPU vs CPU", "run_ids": ["uuid1", "uuid2"], "description": null}
```
Response includes `token` (URL-safe string, `secrets.token_urlsafe(16)`).

### Load by token

`GET /api/comparisons/{token}`:
- Valid token → `200` with comparison data
- Unknown token → `404`

---

## WebSocket (`test_runs.py`)

Use `httpx` WebSocket client or `starlette.testclient.WebSocketTestSession`.

### Normal run progress

Connect to `WS /ws/runs/{id}` while run is `"running"`:
- Events emitted every 2 seconds
- Each event matches schema:
  ```json
  {"run_id": str, "status": str, "completed": int, "total": int,
   "failed": int, "current_tps": float, "elapsed_seconds": float,
   "eta_seconds": float, "server_alive": bool}
  ```
- `server_alive` reflects `is_healthy()` result

### Terminal state closure

When run reaches `"completed"`, `"failed"`, or `"cancelled"`:
- Server emits one final event with terminal status
- Server closes connection with code `1000`

### Unknown run ID

Connect to `WS /ws/runs/nonexistent-id`:
- Server closes immediately with code `1008`
- Close message includes `{"detail": "run not found"}`

---

## Error response shape

All `4xx`/`5xx` responses must return:
```json
{"detail": "human-readable error message"}
```
No full-page error states. Assert `"detail"` key is always present.
