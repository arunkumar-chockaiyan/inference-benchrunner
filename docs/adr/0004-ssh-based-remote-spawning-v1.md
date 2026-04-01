# ADR-0004: SSH-Based Remote Engine Spawning (v1 Architecture)

**Date:** 2026-03-31
**Status:** Accepted
**Context:** Users may want to run benchmarks against remote inference servers (e.g., on a separate machine or cloud instance). We need a lightweight spawning mechanism that doesn't require pre-installed agents.

## Problem

Pre-installed agent requirements:
- Requires deployment to every target machine
- Operational overhead (versioning, updates, monitoring)
- Not feasible for ephemeral cloud instances or user-provided machines
- Forces users to run agents even when not in use

## Decision

**v1 architecture uses SSH + subprocess + nohup:**

```python
# Pseudo-code
async with asyncssh.connect(host, username=user, client_keys=[key_path]) as conn:
    # Start engine via SSH
    cmd = "nohup /path/to/vllm ... > /tmp/vllm.log 2>&1 &"
    await conn.run(cmd)

    # Start sidecar via SSH
    cmd = "nohup otelcol-contrib --config=/tmp/sidecar.yaml ... &"
    await conn.run(cmd)
```

**Mechanics:**
- Backend has SSH credentials (`SSH_DEFAULT_USER`, `SSH_KEY_PATH`)
- `execute_run()` connects to remote host, runs `nohup ... &` commands
- Processes persist after SSH disconnect (nohup redirects output to `/tmp/...`)
- `wait_healthy()` polls engine health via HTTP from local machine
- On cleanup: SSH back in, kill processes by port/PID

**Prerequisites:**
- SSH access to remote machine
- Engine binaries already on remote (or download via SSH)
- `otelcol-contrib` binary on remote

## Consequences

**Positive:**
- No agent deployment required
- Works on any machine with SSH
- Minimal backend complexity
- Scales to many remote machines (one SSH connection per run)
- Doesn't require pre-installed software beyond SSH daemon

**Negative:**
- Process management via SSH is fragile (nohup logs on remote, hard to monitor)
- Cleanup relies on PID/port matching (race conditions possible)
- Network latency increases health check time
- SSH connection failures aren't retried
- No real-time run status from remote process

## v2 Upgrade Path

**Phase 2 or later:** Deploy lightweight FastAPI agents:

```python
# v2: REST-based spawning
async with httpx.AsyncClient() as client:
    await client.post(f"http://{host}:9000/spawn", json={
        "engine": "vllm",
        "model": "mistral",
        ...
    })
```

Agents handle process lifecycle, logging, cleanup locally. Backend doesn't touch SSH.

## Alternatives Considered

1. **Ansible/Chef/Terraform** — Rejected because out of scope; too heavyweight
2. **Docker remote API** — Rejected because assumes Docker; not universal
3. **Kubernetes** — Rejected because v1 should be simple; k8s is v3+

## Related

- Remote spawning: `backend/drivers/remote_driver.py`
- SSH utility: `backend/utils/ssh.py`
- v2 path: documented in `docs/roadmap.md`
