"""
OTel sidecar lifecycle service.

Owns start_sidecar() — renders infra/sidecar.yaml.j2 with run context,
spawns otelcol-contrib as an asyncio subprocess, and returns
(proc, config_path) for cleanup in execute_run()'s finally block.

See docs/spec/04-otel-sidecar.md for full lifecycle and known limitations.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import jinja2

logger = logging.getLogger(__name__)


async def start_sidecar(
    run_id: str,
    engine: str,
    model: str,
    metrics_host: str,
    metrics_port: int,
    engine_host: str,
) -> tuple[asyncio.subprocess.Process, Path]:
    """Render sidecar config, spawn otelcol-contrib, return (proc, config_path).

    Caller (execute_run) must clean up in its finally block:
        sidecar_proc.terminate()
        await sidecar_proc.wait()
        sidecar_config_path.unlink(missing_ok=True)

    Raises RuntimeError if OTEL_COLLECTOR_ENDPOINT is not set.
    Raises jinja2.UndefinedError if any template variable is missing.
    """
    # Template path resolved relative to this file → infra/sidecar.yaml.j2
    template_path = Path(__file__).parent.parent.parent / "infra" / "sidecar.yaml.j2"

    # S-06: StrictUndefined raises at render time if any variable is missing —
    # catches template/call-site mismatches immediately instead of producing a
    # broken config that only fails when otelcol-contrib starts.
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    template = env.from_string(template_path.read_text())

    # S-05: fail fast with a clear message rather than bare KeyError.
    endpoint = os.environ.get("OTEL_COLLECTOR_ENDPOINT")
    if not endpoint:
        raise RuntimeError(
            "OTEL_COLLECTOR_ENDPOINT is not set — add it to .env or environment"
        )

    config_text = template.render(
        run_id=run_id,
        model=model,
        engine=engine,
        metrics_host=metrics_host,
        metrics_port=metrics_port,
        engine_host=engine_host,
        central_collector_endpoint=endpoint,
    )

    config_path = Path(f"/tmp/otel-sidecar-{run_id}.yaml")
    config_path.write_text(config_text)

    # S-02: asyncio.create_subprocess_exec — non-blocking, consistent with async execute_run().
    # S-03: DEVNULL instead of PIPE — PIPE buffers fill under continuous otelcol-contrib
    # output, eventually blocking the child process.
    proc = await asyncio.create_subprocess_exec(
        "otelcol-contrib", "--config", str(config_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    logger.info(
        "sidecar started run_id=%s pid=%s engine=%s metrics=%s:%s",
        run_id, proc.pid, engine, metrics_host, metrics_port,
    )

    # S-04: return config_path so caller can unlink after proc.terminate()
    return proc, config_path
