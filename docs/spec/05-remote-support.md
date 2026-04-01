# Inference Benchrunner — Agent & Remote Support

## Architecture — universal agent

The agent (backend/agent.py) manages engine lifecycle for ALL runs —
local and remote. Location is just config.host. The code path is identical.

```
Local run:   config.host = "localhost"          → agent at localhost:8787
Remote run:  config.host = "gpu-box.ts.net"    → agent at gpu-box.ts.net:8787
```

Remote machines connect via Tailscale (100.x.x.x or *.ts.net MagicDNS).
No SSH. No asyncssh. All agent calls are plain httpx.

## spawn_mode — two values only

```python
spawn_mode: str   # "managed" | "attach"

# "managed" — agent spawns and manages the engine process
#             agent handles: spawn, health, status, teardown
#             used for: vLLM, SGLang, llama.cpp (local and remote)

# "attach"  — engine already running, connect directly
#             no agent involvement in lifecycle
#             teardown is always a no-op
#             used for: Ollama (always), any pre-running engine
```

Ollama is ALWAYS attach mode. Ollama runs as a system service — the agent
does not manage its lifecycle. This is permanent, not a Phase 1 limitation.

## Agent endpoints (backend/agent.py)

```
POST   /spawn                    start engine process
       request:  {"engine": str, "model": str, "port": int,
                  "run_id": str, "extra_args": list[str]}
       response: {"pid": int, "run_id": str}

GET    /run/{run_id}/health      engine health (agent polls localhost internally)
       response: {"healthy": bool, "detail": str, "uptime_s": float}

GET    /run/{run_id}/status      process alive check
       response: {"running": bool, "pid": int}

DELETE /run/{run_id}             stop engine cleanly
       response: {"stopped": bool}

GET    /health                   agent self-health (for docker-compose healthcheck)
       response: {"status": "ok"}
```

## Agent deployment

### Local (docker-compose service)

Agent runs as a service in docker-compose — same image as backend,
different entrypoint. Backend depends_on agent being healthy.

See 10-infrastructure.md for docker-compose config.

### Remote (Tailscale machine)

```bash
pip install fastapi uvicorn httpx
uvicorn agent:app --host 0.0.0.0 --port 8787
# Tailscale handles access control — no firewall config needed
# Benchmark host only needs access to port 8787
```

## Tailscale ACL

With universal agent, benchmark host only needs one rule per remote machine:
  bench-host → remote-machine:8787

Engine ports (8000, 8080, 30000) are internal to the remote machine.
OTel sidecar scrapes engine metrics over Tailscale separately — see 04-otel-sidecar.md.

## Data plane stays direct

stream_prompt() and list_models() always call the engine directly — never
routed through the agent. Agent is control plane only (spawn/health/status/teardown).
Routing token streams through the agent would add latency and create a bottleneck.

## validate_config() — Tailscale warning

For managed and attach modes with a remote host:

```python
if os.environ.get("TAILSCALE_ENABLED") and config.host != "localhost":
    is_tailscale = (
        config.host.endswith(".ts.net") or
        config.host.startswith("100.")
    )
    if not is_tailscale:
        warnings.append(
            f"Host '{config.host}' does not appear to be a Tailscale address. "
            f"Expected 100.x.x.x or *.ts.net. Proceeding anyway."
        )
```
