from __future__ import annotations

import json
import logging
import shutil
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


class OllamaDriver(InferenceEngineDriver):
    """Attach-only driver for Ollama.

    Ollama is a system service — the agent never manages its lifecycle.
    spawn_mode must always be "attach". spawn() always returns owned=False.
    """

    def __init__(self) -> None:
        self._config: RunConfig | None = None

    # ── Control plane ─────────────────────────────────────────────────────────

    async def spawn(self, config: RunConfig, run_id: UUID) -> SpawnResult:
        """Attach to a running Ollama instance. Never calls agent.

        Stores config on the instance so stream_prompt() can access host/port.
        Always returns SpawnResult(owned=False).
        """
        self._config = config
        return SpawnResult(
            owned=False,
            pid=None,
            run_id=str(run_id),
            agent_host=config.host,
            agent_port=config.agent_port,
        )

    def health_url(self, config: RunConfig) -> str:
        """Ollama health endpoint — /api/tags responds 200 when ready."""
        return f"http://{config.host}:{config.port}/api/tags"

    # wait_healthy() inherited — uses health_url() via attach mode path (no agent call)
    # teardown()    inherited — always no-op because owned=False
    # is_running()  inherited — always returns True for attach mode
    # is_healthy()  inherited — calls health_url() directly

    # ── Data plane ────────────────────────────────────────────────────────────

    async def stream_prompt(
        self,
        prompt: str,
        run_id: str,
        params: PromptParams | None = None,
    ) -> AsyncIterator[str | ResponseMeta]:
        """Stream tokens from Ollama /api/generate.

        Yields str chunks for each non-done response fragment, then a final
        ResponseMeta built from the terminal chunk (done=true).

        Requires spawn() to have been called first so self._config is set.
        Raises RuntimeError if not yet configured.
        Raises httpx.TimeoutException if timeout_s is exceeded.
        """
        if self._config is None:
            raise RuntimeError(
                "OllamaDriver.stream_prompt() called before spawn(). "
                "Call spawn(config, run_id) first."
            )

        config = self._config
        timeout = params.timeout_s if params is not None else 120

        url = f"http://{config.host}:{config.port}/api/generate"
        body: dict = {
            "model": config.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": params.temperature if params else 0.7,
                "num_predict": params.max_tokens if params else 512,
                "top_p": params.top_p if params else 1.0,
            },
        }

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=body, timeout=timeout
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(
                            "ollama stream_prompt: could not decode line: %r", line
                        )
                        continue

                    if chunk.get("done"):
                        # Final chunk — build ResponseMeta
                        eval_duration = chunk.get("eval_duration", 0)
                        eval_count = chunk.get("eval_count", 0)
                        engine_tps: float | None = None
                        if eval_duration and eval_duration > 0:
                            engine_tps = eval_count / (eval_duration / 1e9)

                        yield ResponseMeta(
                            prompt_tokens=chunk.get("prompt_eval_count", 0),
                            generated_tokens=eval_count,
                            engine_tps=engine_tps,
                            raw=chunk,
                        )
                        return
                    else:
                        token = chunk.get("response", "")
                        if token:
                            yield token

    async def list_models(self, host: str, port: int) -> list[str]:
        """Return model names from Ollama /api/tags.

        Called only by the sync endpoint — wizard reads from DB registry.
        Returns [] on any error (network, parse, etc.).
        """
        url = f"http://{host}:{port}/api/tags"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", []) if "name" in m]
        except Exception as exc:
            logger.warning("ollama list_models failed for %s:%s — %s", host, port, exc)
            return []

    def get_metrics_port(self, config: RunConfig) -> int:
        """Ollama does not expose Prometheus natively — shim listens on 9091."""
        return 9091

    async def validate_config(
        self, config: RunConfig, db: AsyncSession
    ) -> list[str]:
        """Pre-flight validation. Returns list of error strings (empty = valid).

        Checks (in order):
        1. Model exists in DB registry for this engine + host.
        2. spawn_mode must be "attach" — Ollama is a system service.
        3. Warn if ollama binary is absent on PATH (non-fatal — may be remote).
        4. Warn if remote host is not a Tailscale address.

        Never makes live engine calls.
        """
        errors: list[str] = []

        # 1. Registry check — model must be known for this engine + host
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
                f"Model '{config.model}' not found in registry for "
                f"{config.engine} on {config.host}. "
                f"Sync models first or add manually via "
                f"/api/engines/{config.engine}/models."
            )

        # 2. Ollama must always run in attach mode
        if config.spawn_mode != "attach":
            errors.append(
                "Ollama is a system service — use spawn_mode='attach'. "
                "The agent does not manage Ollama's lifecycle."
            )

        # 3. Warn if ollama binary not found on PATH (non-fatal)
        if shutil.which("ollama") is None:
            errors.append(
                "Warning: 'ollama' binary not found on PATH. "
                "If Ollama is running remotely via API this can be ignored, "
                "but local installations should have 'ollama' on PATH."
            )

        # 4. Tailscale warning for remote hosts
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
