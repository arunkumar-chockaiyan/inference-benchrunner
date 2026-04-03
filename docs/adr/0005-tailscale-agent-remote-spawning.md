# ADR-0005: Tailscale + FastAPI Agent for Remote Engine Management

**Date:** 2026-04-03
**Status:** Accepted

**Supersedes:** ADR-0004 (SSH-based remote spawning)

**Context:** InferenceBenchRunner needs to spawn and manage inference engines on
remote GPU servers. The original SSH-based approach (ADR-0004) was rejected before
implementation in favour of a lightweight agent model.

## Problem

SSH + nohup for remote process management is fragile:
- No structured lifecycle — processes must be tracked by PID/port
- Cleanup is unreliable (SSH reconnect, PID reuse races)
- Requires SSH credentials on the benchmarking host
- No real-time health status from remote process
- asyncssh adds a heavyweight dependency for what is essentially HTTP

## Decision

**Universal FastAPI agent** deployed on every engine host (local and remote).
The agent manages engine lifecycle via plain HTTP. Tailscale provides network
access control — no SSH, no key distribution.

**Architecture:**
```
Benchmarking host (Docker Compose)
  └── backend → httpx → agent:8787  (control plane)
               → engine:port         (data plane — direct, never via agent)

Remote engine host (Tailscale GPU server)
  ├── agent/agent.py  (FastAPI, port 8787, systemd or Docker)
  └── engine process  (spawned by agent on demand)
```

**Agent endpoints:**
```
POST   /spawn              start engine process
GET    /run/{run_id}/health  engine health check
GET    /run/{run_id}/status  process alive check
DELETE /run/{run_id}       stop engine cleanly
GET    /health             agent self-health (exempted from auth)
```

**Key design rules:**
- Local and remote runs are **identical code paths** — `config.host` is the only difference
- `spawn_mode = "managed"` → agent spawns engine; `"attach"` → engine pre-running, agent not used for lifecycle
- Ollama is ALWAYS attach mode — runs as a system service, agent never manages it
- Data plane (`stream_prompt`, `list_models`) calls engine directly — never routed through agent
- Agent authenticated via `X-Agent-Key` shared secret (`AGENT_SECRET_KEY` env var)
- Tailscale ACL is the network boundary; shared key is the application-layer boundary

**Remote deployment:**
- Agent lives in `agent/` directory with its own minimal `requirements.txt` (fastapi, uvicorn, httpx)
- Deployed as systemd service (bare-metal GPU servers) or Docker container (cloud VMs)
- One-time manual provisioning; Tailscale handles ongoing access control

## Consequences

**Positive:**
- Structured HTTP lifecycle — clean spawn, health, status, teardown contract
- `SpawnResult.owned` flag enforces cleanup contract: `owned=False` → teardown is no-op
- No SSH credentials on benchmarking host
- Agent is lightweight (~3 deps), easy to deploy and update
- Tailscale MagicDNS makes host addressing stable across IP changes
- Same agent image used locally (docker-compose) and remotely

**Negative:**
- Agent must be pre-deployed on each remote machine (one-time manual step)
- `AGENT_SECRET_KEY` must be kept in sync across all agent hosts
- Tailscale required on all participating machines

## Alternatives Considered

1. **SSH + asyncssh + nohup** (ADR-0004) — Rejected: fragile lifecycle, credential distribution, no real-time status
2. **Kubernetes / Nomad** — Rejected: too heavyweight; GPU servers are often bare-metal or simple VMs
3. **Docker remote API** — Rejected: assumes Docker everywhere; bare-metal GPU servers often run engines natively
4. **Ansible for provisioning + SSH for lifecycle** — Rejected: too much operational overhead for small teams

## Related

- Agent: `agent/agent.py`
- Spec: `docs/spec/05-remote-support.md`
- Tailscale ACL: `docs/spec/05-remote-support.md` → "Tailscale ACL" section
- `SpawnResult` dataclass: `backend/drivers/base.py`
- Security: `AGENT_SECRET_KEY` in `docs/spec/15-environment.md`
