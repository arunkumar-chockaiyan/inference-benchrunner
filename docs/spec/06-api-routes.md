# Inference Benchrunner — API Routes

## Pagination
All list endpoints use cursor-based pagination: `?cursor=<id>&limit=50`

## Error responses
All API errors return an inline error body: `{"detail": str}`.
No full-page error states in Phase 1.

## Prompts

IMPORTANT: `/api/prompts/import` and `/api/prompts/export` must be registered
BEFORE `/api/prompts/{id}` — FastAPI matches literal segments before path parameters
only when routes are registered in that order.

```
POST   /api/prompts/import             import from CSV/JSON   ← register first
GET    /api/prompts/export             export all as JSON     ← register first

GET    /api/prompts                    list (filter: category, cursor, limit)
POST   /api/prompts                    create
GET    /api/prompts/{id}               get
PUT    /api/prompts/{id}               update
DELETE /api/prompts/{id}               delete

GET    /api/suites                     list
POST   /api/suites                     create
GET    /api/suites/{id}                get with ordered prompts
PUT    /api/suites/{id}                update (auto-increments version)
DELETE /api/suites/{id}                delete
```

## Engines

```
GET    /api/engines                    list supported engines with metadata
GET    /api/engines/{engine}/models          list from DB (filter: ?host=)
POST   /api/engines/{engine}/models/sync     trigger live sync from running engine
                                             params: host (str), port (int)
                                             calls driver.list_models(), upserts to DB
                                             no-op for llamacpp
POST   /api/engines/{engine}/models          add model manually (source="manual")
DELETE /api/engines/{engine}/models/{id}     remove from registry

POST   /api/engines/probe                    test connectivity to host:port
       request:  {"host": str, "port": int, "engine": str}
       response: {"reachable": bool, "latency_ms": float, "error": str | null}
```

## Runs

IMPORTANT: /api/runs/compare registered BEFORE /api/runs/{id} to avoid
FastAPI route conflict (literal "compare" matched as run ID otherwise).

```
POST   /api/runs/compare               compute comparison stats for N run_ids
       request:  {"run_ids": [uuid], "metric": "p99"|"ttft"|"throughput"}
       response: {
         "runs": [{
           "run_id": uuid,
           "avg": float,
           "p99": float,
           "min": float,
           "max": float,
           "stddev": float,
           "sample_count": int
         }]
       }

GET    /api/runs                       list (filter: status, project, engine, tag, cursor, limit)
POST   /api/runs                       create + immediately start
       - calls driver.validate_config() before starting
       - returns 422 with error list if validation fails
GET    /api/runs/{id}                  run detail + live progress
DELETE /api/runs/{id}                  cancel in-progress run
                                       returns 409 if run is already in a terminal
                                       state (completed, failed, cancelled)
GET    /api/runs/{id}/requests         paginated RequestRecords (?cursor&limit)
GET    /api/runs/{id}/export           CSV download (Phase 2)
```

## Comparisons

```
GET    /api/comparisons                list saved comparisons
POST   /api/comparisons                save named comparison
       request:  {"name": str, "run_ids": [uuid], "description": str | null}
       response: {"id": uuid, "name": str, "token": str, "run_ids": [uuid],
                  "created_at": datetime}
       token: URL-safe random string (secrets.token_urlsafe(16)) generated at
              creation — used for shareable links, immutable after creation
GET    /api/comparisons/{token}        load by share token
```

## Projects

```
GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}/runs
```

## WebSocket

```
WS     /ws/runs/{id}                   live run progress stream
```

Event shape (emitted every 2 seconds while running):
```json
{
  "run_id": "uuid",
  "status": "running",
  "completed": 42,
  "total": 100,
  "failed": 1,
  "current_tps": 847.3,
  "elapsed_seconds": 34,
  "eta_seconds": 22,
  "server_alive": true
}
```

### WebSocket lifecycle

- Server emits events every 2 seconds while `status == "running"`.
- When the run reaches a terminal state (`completed`, `failed`, `cancelled`), the
  server emits one final event with the terminal status, then closes the connection
  with code 1000 (normal closure).
- Client should reconnect on unexpected closure (code ≠ 1000) with exponential
  backoff — the backend may have restarted mid-run.
- If the run does not exist, the server closes immediately with code 1008 (policy
  violation) and `{"detail": "run not found"}`.
