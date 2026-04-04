from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from drivers.base import (
    InferenceEngineDriver,
    PromptParams,
    ResponseMeta,
    SpawnResult,
    _agent_headers,
)
from models import EngineModel, RunConfig

logger = logging.getLogger(__name__)


class LlamaCppDriver(InferenceEngineDriver):
    """Driver for llama.cpp server (llama-server).

    Supports both managed mode (agent spawns the server) and attach mode
    (server already running). Exposes Prometheus /metrics on the same port
    via the --metrics flag.
    """

    def __init__(self) -> None:
        self._config: RunConfig | None = None

    # ── Control plane ─────────────────────────────────────────────────────────

    async def spawn(self, config: RunConfig, run_id: UUID) -> SpawnResult:
        """Start or attach to llama-server via agent.

        managed: POST /spawn to agent → SpawnResult(owned=True)
        attach:  no agent call        → SpawnResult(owned=False)
        """
        self._config = config

        if config.spawn_mode == "managed":
            url = f"http://{config.host}:{config.agent_port}/spawn"
            body = {
                "engine": "llamacpp",
                "model": config.model,
                "port": config.port,
                "run_id": str(run_id),
                "extra_args": ["--metrics", "--ctx-size", "4096"],
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers=_agent_headers(),
                    timeout=30,
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Agent spawn failed for run {run_id}: "
                    f"HTTP {resp.status_code} — {resp.text}"
                )
            data = resp.json()
            return SpawnResult(
                owned=True,
                pid=data["pid"],
                run_id=str(run_id),
                agent_host=config.host,
                agent_port=config.agent_port,
            )

        # attach mode — engine already running, nothing to do
        return SpawnResult(
            owned=False,
            pid=None,
            run_id=str(run_id),
            agent_host=config.host,
            agent_port=config.agent_port,
        )

    # health_url() inherited from ABC:  http://{host}:{port}/health  ✓

    # teardown() / wait_healthy() / is_running() / is_healthy() all inherited

    # ── Data plane ────────────────────────────────────────────────────────────

    async def stream_prompt(
        self,
        prompt: str,
        run_id: str,
        params: PromptParams | None = None,
    ) -> AsyncIterator[str | ResponseMeta]:
        """Stream tokens from llama-server /completion endpoint.

        Yields str chunks for each non-stop chunk, then a final ResponseMeta
        built from the terminal chunk (stop: true).
        """
        config = self._config
        if config is None:
            raise RuntimeError(
                "LlamaCppDriver.stream_prompt() called before spawn(). "
                "self._config is not set."
            )

        timeout = params.timeout_s if params is not None else 120
        url = f"http://{config.host}:{config.port}/completion"
        body: dict = {
            "prompt": prompt,
            "n_predict": params.max_tokens if params is not None else 512,
            "stream": True,
            "temperature": params.temperature if params is not None else 0.7,
            "top_p": params.top_p if params is not None else 1.0,
        }

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                url,
                json=body,
                timeout=timeout,
            ) as response:
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    # llama-server SSE lines are prefixed with "data: "
                    if line.startswith("data: "):
                        line = line[len("data: "):]

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug(
                            "llamacpp stream_prompt: skipping non-JSON line: %r", line
                        )
                        continue

                    if chunk.get("stop"):
                        # Terminal chunk — build and yield ResponseMeta
                        yield ResponseMeta(
                            prompt_tokens=chunk["tokens_evaluated"],
                            generated_tokens=chunk["tokens_predicted"],
                            engine_tps=chunk["timings"]["predicted_per_second"],
                            raw=chunk,
                        )
                        return

                    content = chunk.get("content", "")
                    if content:
                        yield content

    async def list_models(self, host: str, port: int) -> list[str]:
        """llama.cpp has no model discovery API.

        Models must be registered manually via /api/engines/llamacpp/models.
        Always returns an empty list.
        """
        return []

    def get_metrics_port(self, config: RunConfig) -> int:
        """llama-server exposes /metrics on the same port when started with --metrics."""
        return config.port

    async def validate_config(
        self, config: RunConfig, db: AsyncSession
    ) -> list[str]:
        """Pre-flight validation. Returns a list of error strings (empty = valid).

        Checks:
          1. model is set
          2. port is set
          3. model exists in the EngineModel registry for this engine + host
          4. Tailscale warning if host is remote but not a Tailscale address
        """
        errors: list[str] = []

        # 1. model must be non-empty
        if not config.model:
            errors.append("model is required for llamacpp")

        # 2. port must be set (non-zero)
        if not config.port:
            errors.append("port is required for llamacpp")

        # 3. registry check — no live engine call needed
        result = await db.execute(
            select(EngineModel).where(
                EngineModel.engine == config.engine,
                EngineModel.host == config.host,
                EngineModel.model_id == config.model,
            )
        )
        known = result.scalar_one_or_none()
        if not known:
            errors.append(
                f"Model '{config.model}' not found in registry for llamacpp on "
                f"{config.host}. Add manually via /api/engines/llamacpp/models."
            )

        # 4. Tailscale warning for non-localhost remote hosts
        if config.host not in ("localhost", "127.0.0.1"):
            is_tailscale = (
                config.host.endswith(".ts.net")
                or config.host.startswith("100.")
            )
            if not is_tailscale:
                errors.append(
                    f"Host '{config.host}' does not appear to be a Tailscale address. "
                    f"Expected 100.x.x.x or *.ts.net. Remote access without Tailscale "
                    f"is unsupported. Proceeding anyway."
                )

        return errors
