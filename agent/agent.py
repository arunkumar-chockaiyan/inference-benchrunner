from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="InferenceBenchRunner Agent")

# run_id -> asyncio subprocess handle
_processes: dict[str, asyncio.subprocess.Process] = {}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def verify_agent_key(x_agent_key: str = Header(...)) -> None:
    expected = os.environ.get("AGENT_SECRET_KEY", "")
    if not expected:
        raise RuntimeError("AGENT_SECRET_KEY is not set on the agent host")
    if not secrets.compare_digest(x_agent_key, expected):
        raise HTTPException(status_code=401, detail="Invalid agent key")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SpawnRequest(BaseModel):
    engine: str
    model: str
    port: int
    run_id: str
    extra_args: list[str] = []


class SpawnResponse(BaseModel):
    pid: int
    run_id: str


class HealthResponse(BaseModel):
    healthy: bool
    detail: str
    uptime_s: float


class StatusResponse(BaseModel):
    running: bool
    pid: int | None


class StopResponse(BaseModel):
    stopped: bool
    method: str


class AgentHealthResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=AgentHealthResponse)
async def agent_health() -> dict[str, Any]:
    """Agent self-health check — no auth, used by docker-compose healthcheck."""
    return {"status": "ok"}


@app.post(
    "/spawn",
    response_model=SpawnResponse,
    dependencies=[Depends(verify_agent_key)],
)
async def spawn(req: SpawnRequest) -> dict[str, Any]:
    """Spawn an inference engine process and register it under run_id."""
    if req.run_id in _processes:
        raise HTTPException(status_code=409, detail="run_id already registered")

    engine = req.engine.lower()
    model = req.model
    port = req.port
    extra = req.extra_args

    if engine == "llamacpp":
        cmd = ["llama-server", "--model", model, "--port", str(port), "--metrics"] + extra
    elif engine == "vllm":
        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", model,
            "--port", str(port),
        ] + extra
    elif engine == "sglang":
        cmd = [
            "python", "-m", "sglang.launch_server",
            "--model-path", model,
            "--port", str(port),
        ] + extra
    else:
        raise HTTPException(status_code=422, detail=f"unknown engine: {engine}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    _processes[req.run_id] = proc

    return {"pid": proc.pid, "run_id": req.run_id}


@app.get(
    "/run/{run_id}/health",
    response_model=HealthResponse,
    dependencies=[Depends(verify_agent_key)],
)
async def run_health(run_id: str) -> dict[str, Any]:
    """Return whether the engine process for run_id is alive."""
    if run_id not in _processes:
        return {"healthy": False, "detail": "run not registered", "uptime_s": 0.0}

    proc = _processes[run_id]
    if proc.returncode is not None:
        return {"healthy": False, "detail": "process exited", "uptime_s": 0.0}

    return {"healthy": True, "detail": "running", "uptime_s": 0.0}


@app.get(
    "/run/{run_id}/status",
    response_model=StatusResponse,
    dependencies=[Depends(verify_agent_key)],
)
async def run_status(run_id: str) -> dict[str, Any]:
    """Return process alive status and PID for run_id."""
    if run_id not in _processes:
        return {"running": False, "pid": None}

    proc = _processes[run_id]
    if proc.returncode is not None:
        return {"running": False, "pid": None}

    return {"running": True, "pid": proc.pid}


@app.delete(
    "/run/{run_id}",
    response_model=StopResponse,
    dependencies=[Depends(verify_agent_key)],
)
async def stop_run(run_id: str) -> dict[str, Any]:
    """Stop the engine process for run_id and deregister it."""
    if run_id not in _processes:
        return {"stopped": True, "method": "not_registered"}

    proc = _processes[run_id]

    if proc.returncode is not None:
        # Process already dead — clean up the registration
        del _processes[run_id]
        return {"stopped": True, "method": "already_dead"}

    # Attempt graceful shutdown with SIGTERM, escalate to SIGKILL on timeout
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=10.0)
        method = "sigterm"
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        method = "sigkill"

    del _processes[run_id]
    return {"stopped": True, "method": method}
