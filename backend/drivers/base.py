from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from models import RunConfig

logger = logging.getLogger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class PromptParams:
    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 1.0
    timeout_s: int = 120   # per-request timeout — prevents hung requests


@dataclass
class ResponseMeta:
    prompt_tokens: int
    generated_tokens: int
    engine_tps: float | None = None  # engine-reported TPS
                                     # available: Ollama, llama.cpp
                                     # not available: vLLM, SGLang (use wall-clock TPS)
    raw: dict = field(default_factory=dict)  # raw final chunk for debugging


@dataclass
class SpawnResult:
    owned: bool        # True = agent spawned it; teardown() must kill it
                       # False = attach mode; teardown() is always a no-op
    pid: int | None    # engine process PID reported by agent (None for attach)
    run_id: str        # run identifier used with agent endpoints
    agent_host: str    # host where agent runs (localhost or Tailscale addr)
    agent_port: int    # agent port (default 8787)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _agent_headers() -> dict[str, str]:
    """Return X-Agent-Key header for agent auth. Empty dict if key not set."""
    key = os.environ.get("AGENT_SECRET_KEY", "")
    return {"X-Agent-Key": key} if key else {}


# ── ABC ───────────────────────────────────────────────────────────────────────


class InferenceEngineDriver(ABC):

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        model_id: str | None = None,
    ):
        """Initialize driver with optional host, port, and model_id for testing/config."""
        self.host = host
        self.port = port
        self.model_id = model_id
        self.owned = False  # Default to attach mode; spawn() will set this
        self.process = None  # Optional process handle for managed mode

    # ── Control plane (via agent) ─────────────────────────────────────────────

    @abstractmethod
    async def spawn(self, config: RunConfig, run_id: UUID) -> SpawnResult:
        """Start or attach to inference server via agent.

        managed mode: POST to agent /spawn → SpawnResult(owned=True)
        attach mode:  no agent call       → SpawnResult(owned=False)

        Agent host = config.host (localhost or Tailscale addr), port = config.agent_port.
        run_id: Run.id (not RunConfig.id) — registered with agent and used in all
        subsequent agent calls (health, status, teardown).
        """

    async def wait_healthy(
        self,
        config: RunConfig,
        run_id: UUID,
        timeout: int | None = None,
    ) -> None:
        """Poll until engine is healthy or timeout exceeded.

        managed mode: polls agent /run/{run_id}/health every 1s
                      (agent polls engine on localhost internally — benchmark host
                       never hits engine port directly during health check)
        attach mode:  polls engine health_url() directly

        Swallows all per-poll errors (ConnectionRefused, 503 expected during startup).
        Raises TimeoutError when deadline exceeded.
        Uses config.health_timeout_s (default 180s) if timeout not passed.
        run_id: Run.id — must match the run_id passed to spawn().
        """
        deadline = time.monotonic() + (timeout or config.health_timeout_s or 180)

        if config.spawn_mode == "managed":
            url = f"http://{config.host}:{config.agent_port}/run/{run_id}/health"
            headers = _agent_headers()
        else:
            url = self.health_url(config)
            headers = {}

        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    return
            except Exception:
                pass  # ConnectionRefused, timeout, 503 — expected during startup
            await asyncio.sleep(1)

        raise TimeoutError(
            f"{config.engine} on {config.host}:{config.port} did not become "
            f"healthy within {timeout or config.health_timeout_s or 180}s"
        )

    def health_url(self, config: RunConfig) -> str:
        """Direct engine health endpoint — used for attach mode only.
        Override in OllamaDriver (uses /api/tags instead of /health).
        """
        return f"http://{config.host}:{config.port}/health"

    async def teardown(self, config: RunConfig, result: SpawnResult) -> None:
        """Stop engine if owned. No-op if attach mode (result.owned=False).

        managed mode: DELETE http://{agent_host}:{agent_port}/run/{run_id}
        attach mode:  log and return — never kill a server we didn't start.

        Swallows agent errors — teardown runs in finally block and must not
        mask the original run exception. execute_run() sets cleanup_warning
        on the Run record if this raises.
        """
        if not result.owned:
            logger.info("attach mode — leaving %s:%s running", config.host, config.port)
            return

        url = f"http://{result.agent_host}:{result.agent_port}/run/{result.run_id}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(url, headers=_agent_headers(), timeout=15)
            if resp.status_code not in (200, 404):
                logger.warning(
                    "teardown: agent returned %s for run %s",
                    resp.status_code, result.run_id,
                )
        except Exception as e:
            logger.error(
                "teardown: could not reach agent for run %s: %s",
                result.run_id, e,
            )
            # execute_run() sets cleanup_warning on the Run record after catching this

    async def is_running(self, config: RunConfig, result: SpawnResult) -> bool:
        """Process-level liveness check via agent. Fast — no engine call.

        managed mode: GET agent /run/{run_id}/status → {"running": bool}
        attach mode:  always returns True — use is_healthy() for attach liveness

        Returns False on any error (agent unreachable = treat process as dead).
        """
        if not result.owned:
            return True  # attach mode — assume alive; is_healthy() is the signal

        url = (
            f"http://{result.agent_host}:{result.agent_port}"
            f"/run/{result.run_id}/status"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=_agent_headers(), timeout=5)
            return resp.json().get("running", False)
        except Exception:
            return False  # agent unreachable = treat process as dead

    async def is_healthy(self, config: RunConfig) -> bool:
        """HTTP health endpoint check — always calls engine directly, never via agent.

        Used for: mid-run watchdog, attach mode liveness, WebSocket server_alive field.
        Returns False on any error instead of raising.
        """
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.health_url(config), timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    # ── Data plane (direct to engine, never via agent) ────────────────────────

    @abstractmethod
    async def stream_prompt(
        self,
        prompt: str,
        run_id: str,
        params: PromptParams | None = None,
    ) -> AsyncIterator[str | ResponseMeta]:
        """Stream response tokens as str chunks, then a final ResponseMeta.

        Always calls engine directly — never routed through agent.
        Raises httpx.TimeoutException if params.timeout_s exceeded.
        execute_run() owns RequestRecord construction from this stream.
        """

    @abstractmethod
    async def list_models(self, host: str, port: int) -> list[str]:
        """Return available model IDs for this engine at host:port.

        Called ONLY by the sync endpoint — wizard reads from EngineModel DB registry.
        llamacpp always returns [] (no discovery API).
        """

    @abstractmethod
    async def validate_config(
        self, config: RunConfig, db: AsyncSession
    ) -> list[str]:
        """Pre-flight check. Returns list of error strings (empty = valid).

        Never makes live engine calls. Works for both managed and attach modes.
        db: AsyncSession injected at call time — used for EngineModel registry checks.
        """

    @abstractmethod
    def get_metrics_port(self, config: RunConfig) -> int:
        """Return the port this engine exposes Prometheus /metrics on.
        Called by execute_run() to configure the OTel sidecar scrape target.
        """
