# QA Spec — Agent & Remote Support

Source: `docs/spec/05-remote-support.md`, `backend/agent.py`

---

## Agent endpoint tests (`test_agent.py`)

Use FastAPI `TestClient` against `agent/agent.py`.

### POST /spawn

| Scenario | Expected |
|----------|----------|
| Valid request with correct `X-Agent-Key` | `200 {"pid": int, "run_id": str}` |
| Missing `X-Agent-Key` header | `401` |
| Wrong `X-Agent-Key` value | `401` |
| Engine command fails to start | `500` or structured error |

Request body:
```json
{"engine": "vllm", "model": "meta-llama/Llama-3-8B", "port": 8000,
 "run_id": "abc-123", "extra_args": []}
```

Assert `pid` is a positive integer in response.

### GET /run/{run_id}/health

| Scenario | Expected |
|----------|----------|
| Engine healthy | `200 {"healthy": true, "detail": "...", "uptime_s": float}` |
| Engine not yet healthy | `200 {"healthy": false, ...}` |
| Unknown `run_id` | `404` |
| Missing auth key | `401` |

### GET /run/{run_id}/status

| Scenario | Expected |
|----------|----------|
| Process running | `200 {"running": true, "pid": int}` |
| Process dead | `200 {"running": false, "pid": int}` |
| Unknown `run_id` | `404` |
| Missing auth key | `401` |

### DELETE /run/{run_id}

| Scenario | Expected |
|----------|----------|
| Process running → SIGTERM successful | `200 {"stopped": true, "method": "sigterm"}` |
| Process already dead | `200 {"stopped": true, "method": "already_dead"}` |
| SIGTERM ignored → SIGKILL | `200 {"stopped": true, "method": "sigkill"}` |
| Unknown `run_id` | `404` |
| Missing auth key | `401` |

Idempotency: calling DELETE twice on same `run_id` → second call returns `200` (not error).

### GET /health (agent self-health)

| Scenario | Expected |
|----------|----------|
| Agent running | `200 {"status": "ok"}` |
| **No `X-Agent-Key` required** | Exempt from auth — docker-compose healthcheck has no credentials |

---

## Authentication (`test_agent.py`)

### Key comparison

- `secrets.compare_digest()` must be used (constant-time) — verify via code review / grep
- Correct key → 200
- Empty key header → 401
- Key with extra whitespace → 401 (exact match required)

### Missing AGENT_SECRET_KEY on agent host

- `AGENT_SECRET_KEY` env var not set → `RuntimeError` at startup or on first protected request
- Must NOT silently accept any key

### Shared key — backend to agent

All driver httpx calls to agent must include:
```python
headers = {"X-Agent-Key": os.environ["AGENT_SECRET_KEY"]}
```
Assert this header is present in every agent call from the driver tests (check via `respx` captured requests).

---

## spawn_mode rules

| spawn_mode | Engine | Who spawns | teardown |
|------------|--------|-----------|---------|
| `managed` | llamacpp, vllm, sglang | agent | agent DELETE |
| `attach` | ollama (always) | nobody | no-op |
| `attach` | any (pre-running) | nobody | no-op |

Test: `spawn_mode="managed"` with Ollama driver → `validate_config()` returns error.
Test: `spawn_mode="attach"` → no POST to agent `/spawn` made.

---

## Tailscale address validation

### validate_config() Tailscale warning

| `config.host` | Expected warning |
|---------------|-----------------|
| `"localhost"` | No warning |
| `"127.0.0.1"` | No warning |
| `"100.64.0.1"` | No warning (valid Tailscale IP) |
| `"gpu-box.ts.net"` | No warning (valid MagicDNS) |
| `"192.168.1.100"` | Warning: does not appear to be Tailscale address |
| `"gpu-box.internal"` | Warning |

### validate_config() never makes live engine calls

Mock all httpx at driver level. Assert zero HTTP requests made during `validate_config()`.

---

## Remote run code path

Local and remote runs use the same code path. Only `config.host` differs.

Test: same driver with `config.host="localhost"` vs `config.host="100.64.0.1"`.
Assert: both produce the same agent URL format `http://{host}:{agent_port}/spawn`.
Assert: no SSH or asyncssh calls anywhere in the codebase (grep for `asyncssh` → zero results).

---

## Agent teardown — error swallowing

In `teardown()`:
- Agent unreachable (connection refused) → exception swallowed, NOT re-raised
- `cleanup_warning` is set on `Run` record if teardown failed
- Run's primary exception (if any) is NOT masked by teardown failure

Test:
```python
async def test_teardown_swallows_agent_error(mock_agent_down):
    result = SpawnResult(owned=True, ...)
    await driver.teardown(config, result)  # must not raise
    # verify cleanup_warning set on Run
```
