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


class SGLangDriver(InferenceEngineDriver):
    """Driver for SGLang inference server.

    SGLang exposes an OpenAI-compatible API — stream_prompt() is identical
    to VllmDriver. spawn_mode supports both "managed" and "attach".
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        model_id: str | None = None,
    ) -> None:
        super().__init__(host=host, port=port, model_id=model_id)
        self._config: RunConfig | None = None

    # ── Control plane ─────────────────────────────────────────────────────────

    async def spawn(self, config: RunConfig, run_id: UUID) -> SpawnResult:
        """Start or attach to SGLang via agent.

        managed mode: POSTs to agent /spawn → SpawnResult(owned=True, pid=...)
        attach mode:  no agent call        → SpawnResult(owned=False)

        Stores config on the instance so stream_prompt() can access host/port.
        """
        self._config = config

        if config.spawn_mode == "managed":
            url = f"http://{config.host}:{config.agent_port}/spawn"
            body = {
                "engine": "sglang",
                "model": config.model,
                "port": config.port,
                "run_id": str(run_id),
                "extra_args": [],
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers=_agent_headers(),
                    timeout=30,
                )
            resp.raise_for_status()
            data = resp.json()
            return SpawnResult(
                owned=True,
                pid=data["pid"],
                run_id=str(run_id),
                agent_host=config.host,
                agent_port=config.agent_port,
            )

        # attach mode — engine already running, nothing to start
        return SpawnResult(
            owned=False,
            pid=None,
            run_id=str(run_id),
            agent_host=config.host,
            agent_port=config.agent_port,
        )

    # health_url() inherited from ABC: http://{host}:{port}/health
    # wait_healthy() inherited — managed uses agent /run/{run_id}/health,
    #                            attach polls health_url() directly
    # teardown()    inherited — DELETE agent /run/{run_id} if owned, no-op if not
    # is_running()  inherited — agent /run/{run_id}/status if owned, True if attach
    # is_healthy()  inherited — calls health_url() directly

    # ── Data plane ────────────────────────────────────────────────────────────

    async def stream_prompt(
        self,
        prompt: str,
        run_id: str,
        params: PromptParams | None = None,
    ) -> AsyncIterator[str | ResponseMeta]:
        """Stream tokens from SGLang /v1/chat/completions (OpenAI-compatible SSE).

        Yields str chunks for each token delta, then a final ResponseMeta
        built from the usage chunk (present because stream_options.include_usage=true).

        Requires spawn() to have been called first so self._config is set.
        Raises RuntimeError if not yet configured.
        Raises httpx.TimeoutException if params.timeout_s is exceeded.
        """
        if self._config is None:
            raise RuntimeError(
                "SGLangDriver.stream_prompt() called before spawn(). "
                "Call spawn(config, run_id) first."
            )

        config = self._config
        p = params if params is not None else PromptParams()
        timeout = p.timeout_s

        url = f"http://{config.host}:{config.port}/v1/chat/completions"
        body = {
            "model": config.model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": prompt}],
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "top_p": p.top_p,
        }

        usage: dict = {}

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=body, timeout=timeout
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue

                    payload = line[len("data: "):]

                    if payload.strip() == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        logger.warning(
                            "sglang stream_prompt: could not decode SSE payload: %r",
                            payload,
                        )
                        continue

                    # Capture usage when present (final stats chunk)
                    if chunk.get("usage") is not None:
                        usage = chunk["usage"]

                    # Yield token delta content if present
                    choices = chunk.get("choices") or []
                    for choice in choices:
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield content

        yield ResponseMeta(
            prompt_tokens=usage.get("prompt_tokens", 0),
            generated_tokens=usage.get("completion_tokens", 0),
            engine_tps=None,  # SGLang does not report TPS; caller uses wall-clock
            raw=usage,
        )

    async def list_models(self, host: str, port: int) -> list[str]:
        """Return model IDs from SGLang /v1/models.

        Called only by the sync endpoint — wizard reads from DB registry.
        Returns [] on any error (network, parse, etc.).
        """
        url = f"http://{host}:{port}/v1/models"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", []) if "id" in m]
        except Exception as exc:
            logger.warning("sglang list_models failed for %s:%s — %s", host, port, exc)
            return []

    def get_metrics_port(self, config: RunConfig) -> int:
        """SGLang exposes Prometheus /metrics on the same port as the API."""
        return config.port

    async def validate_config(
        self, config: RunConfig, db: AsyncSession
    ) -> list[str]:
        """Pre-flight validation. Returns list of error strings (empty = valid).

        Checks (in order):
        1. Model exists in DB registry for this engine + host.
        2. Port is set (non-zero).
        3. Warn if remote host is not a Tailscale address.

        Never makes live engine calls.
        """
        errors: list[str] = []

        # 1. Registry check — model must be known for this engine
        result = await db.execute(
            select(EngineModel).where(
                EngineModel.engine == config.engine,
                EngineModel.model_id == config.model,
            )
        )
        if not result.scalar_one_or_none():
            errors.append(
                f"Model '{config.model}' not found in registry for sglang. "
                f"Sync models first or add manually via /api/engines/sglang/models."
            )

        # 2. Port check — must be explicitly configured
        if not config.port:
            errors.append(
                "SGLang requires an explicit port. Set port in the run config."
            )

        # 3. Tailscale warning for remote hosts
        if config.host not in ("localhost", "127.0.0.1"):
            is_tailscale = (
                config.host.endswith(".ts.net")
                or config.host.startswith("100.")
            )
            if not is_tailscale:
                errors.append(
                    f"Host '{config.host}' does not appear to be a Tailscale address. "
                    f"Expected 100.x.x.x or *.ts.net. "
                    f"Remote access without Tailscale is unsupported. Proceeding anyway."
                )

        return errors
