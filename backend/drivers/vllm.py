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


class VllmDriver(InferenceEngineDriver):
    """Driver for vLLM — OpenAI-compatible inference server."""

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
        self._config = config

        if config.spawn_mode == "managed":
            url = f"http://{config.host}:{config.agent_port}/spawn"
            body = {
                "engine": "vllm",
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

        # attach mode — no agent call
        return SpawnResult(
            owned=False,
            pid=None,
            run_id=str(run_id),
            agent_host=config.host,
            agent_port=config.agent_port,
        )

    # health_url() uses the ABC default: http://{host}:{port}/health — no override needed

    # ── Data plane ────────────────────────────────────────────────────────────

    async def stream_prompt(
        self,
        prompt: str,
        run_id: str,
        params: PromptParams | None = None,
    ) -> AsyncIterator[str | ResponseMeta]:
        config = self._config
        if config is None:
            raise RuntimeError("VllmDriver.stream_prompt() called before spawn()")

        host = config.host
        port = config.port
        model = config.model
        timeout = params.timeout_s if params is not None else 120

        url = f"http://{host}:{port}/v1/chat/completions"
        body = {
            "model": model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": prompt}],
            "temperature": params.temperature if params is not None else 0.7,
            "max_tokens": params.max_tokens if params is not None else 512,
            "top_p": params.top_p if params is not None else 1.0,
        }

        usage: dict | None = None

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                url,
                json=body,
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    payload = line[6:]  # strip "data: " prefix

                    if payload == "[DONE]":
                        break

                    chunk = json.loads(payload)

                    # Capture usage when the final chunk populates it
                    # (requires stream_options.include_usage=true)
                    if chunk.get("usage") is not None:
                        usage = chunk["usage"]

                    choices = chunk.get("choices")
                    if choices:
                        delta = choices[0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta

        yield ResponseMeta(
            prompt_tokens=usage["prompt_tokens"] if usage else 0,
            generated_tokens=usage["completion_tokens"] if usage else 0,
            engine_tps=None,  # vLLM does not report internal TPS
            raw=usage if usage else {},
        )

    async def list_models(self, host: str, port: int) -> list[str]:
        url = f"http://{host}:{port}/v1/models"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
        data = resp.json()
        return [entry["id"] for entry in data.get("data", [])]

    def get_metrics_port(self, config: RunConfig) -> int:
        return config.port

    async def validate_config(
        self, config: RunConfig, db: AsyncSession
    ) -> list[str]:
        errors: list[str] = []

        # Registry check
        result = await db.execute(
            select(EngineModel).where(
                EngineModel.engine == config.engine,
                EngineModel.host == config.host,
                EngineModel.model_id == config.model,
            )
        )
        if not result.scalar_one_or_none():
            errors.append(
                f"Model '{config.model}' not found in registry for vllm on {config.host}."
            )

        # Port check
        if not config.port:
            errors.append("port is required for vllm")

        # Tailscale warning for remote hosts
        host = config.host
        if host not in ("localhost", "127.0.0.1") and not (
            host.startswith("100.") or host.endswith(".ts.net")
        ):
            errors.append(
                f"Remote host '{host}' does not appear to be a Tailscale address "
                "(expected 100.x.x.x or *.ts.net). Remote access requires Tailscale."
            )

        return errors
