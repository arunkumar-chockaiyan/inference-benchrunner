# Inference Benchrunner — Agent & Remote Support

## Architecture — universal agent

The agent (agent/agent.py) manages engine lifecycle for ALL runs —
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

## Agent endpoints (agent/agent.py)

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

The agent is a **one-time manual deployment** — install once, leave running.
The "no SSH at runtime" rule applies to the data plane; SSH for initial provisioning
is fine. After setup the benchmarking host communicates with the agent exclusively
over Tailscale HTTP.

The remote machine only needs the `agent/` directory — not the full backend.
`agent/requirements.txt` contains only `fastapi`, `uvicorn`, `httpx`.

#### Option A — systemd (recommended for bare-metal GPU servers)

Preferred when the remote machine runs inference engines directly on the host.
The agent and engines share the same process namespace, GPU drivers are visible
without device passthrough, and DCGM/nvidia-smi scrapers co-exist naturally.

```bash
# 1. Copy agent directory to remote machine
scp -r agent/ user@gpu-box.ts.net:/opt/bench-agent/

# 2. Install dependencies
ssh user@gpu-box.ts.net "pip install -r /opt/bench-agent/requirements-agent.txt"

# 3. Create .env with the shared key
ssh user@gpu-box.ts.net "echo 'AGENT_SECRET_KEY=<key>' > /opt/bench-agent/.env"
```

Systemd unit (`/etc/systemd/system/bench-agent.service`):
```ini
[Unit]
Description=InferenceBenchRunner Agent
After=network.target tailscaled.service

[Service]
ExecStart=uvicorn agent:app --host 0.0.0.0 --port 8787
WorkingDirectory=/opt/bench-agent
EnvironmentFile=/opt/bench-agent/.env
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now bench-agent
```

#### Option B — Docker (recommended for cloud VMs / containerised environments)

Preferred when the remote machine already manages workloads via Docker.
Requires `--gpus all` and `nvidia-container-toolkit` for GPU access.

```bash
docker run -d --restart=always \
  --name bench-agent \
  -p 8787:8787 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e AGENT_SECRET_KEY=<key> \
  bench-agent:latest   # built from agent/Dockerfile — minimal deps only
```

`/var/run/docker.sock` is required if the agent spawns engine containers.
For bare-metal engine processes (vLLM/SGLang launched directly), the socket
is not needed and should be omitted.

## Tailscale ACL

The benchmarking host needs access to three port groups on each remote machine:

```
bench-host → remote-machine:8787          # agent (control plane)
bench-host → remote-machine:8080          # llama.cpp /metrics + stream_prompt (data plane)
bench-host → remote-machine:8000          # vLLM /metrics + stream_prompt (data plane)
bench-host → remote-machine:30000         # SGLang /metrics + stream_prompt (data plane)
```

Engine ports are required for two reasons:
1. `stream_prompt()` and `list_models()` call the engine **directly** from the benchmarking host (data plane is never routed through the agent).
2. The OTel sidecar runs on the benchmarking host and scrapes the remote engine's `/metrics` endpoint over Tailscale.

Ollama is always local — no remote Tailscale port needed for Ollama.

## Agent security — shared key

The agent uses a pre-shared key for service-to-service authentication. Every
request from the backend to the agent must carry the header `X-Agent-Key: <secret>`.
The agent rejects requests without it with HTTP 401.

```python
# agent.py — dependency applied to all routes except GET /health
import os, secrets
from fastapi import Header, HTTPException

async def verify_agent_key(x_agent_key: str = Header(...)):
    expected = os.environ.get("AGENT_SECRET_KEY", "")
    if not expected:
        raise RuntimeError("AGENT_SECRET_KEY is not set on the agent host")
    if not secrets.compare_digest(x_agent_key, expected):
        raise HTTPException(status_code=401, detail="Invalid agent key")
```

- `GET /health` is exempted — used by docker-compose healthcheck, which has no credentials.
- `AGENT_SECRET_KEY` must be the same value in `.env` on the benchmarking host and on every remote agent host.
- Use `secrets.compare_digest()` — constant-time comparison prevents timing attacks.
- Tailscale ACL remains the network boundary; the shared key is the application-layer boundary on top.

All driver httpx calls to the agent must include the key:

```python
headers = {"X-Agent-Key": os.environ["AGENT_SECRET_KEY"]}
await httpx_client.post(f"http://{config.host}:{config.agent_port}/spawn",
                        json=payload, headers=headers)
```

## Data plane stays direct

stream_prompt() and list_models() always call the engine directly — never
routed through the agent. Agent is control plane only (spawn/health/status/teardown).
Routing token streams through the agent would add latency and create a bottleneck.

## validate_config() — Tailscale warning

For managed and attach modes with a remote host. No env var gate — the check
runs whenever the host is not localhost, so it cannot be silently disabled by
a missing env var:

```python
if config.host not in ("localhost", "127.0.0.1"):
    is_tailscale = (
        config.host.endswith(".ts.net") or
        config.host.startswith("100.")
    )
    if not is_tailscale:
        warnings.append(
            f"Host '{config.host}' does not appear to be a Tailscale address. "
            f"Expected 100.x.x.x or *.ts.net. Remote access without Tailscale "
            f"is unsupported. Proceeding anyway."
        )
```
