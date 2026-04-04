"""
Run execution service.

Owns execute_run(), engine_watchdog(), and recover_stale_runs().
execute_run() is the top-level coordinator: validate → spawn → shim →
warmup → sidecar → benchmark. collect_record() (collector.py) handles
per-request streaming and writing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import AsyncSessionLocal
from drivers import get_driver
from drivers.base import InferenceEngineDriver, SpawnResult
from models import Prompt, PromptSuite, RequestRecord, Run, RunConfig, SuitePrompt
from services.collector import collect_record
from services.sidecar import start_sidecar

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal DB helpers
# ---------------------------------------------------------------------------

async def _update_run(db: AsyncSession, run_id: UUID, **kwargs: object) -> None:
    """SET arbitrary Run columns and commit."""
    await db.execute(update(Run).where(Run.id == run_id).values(**kwargs))
    await db.commit()


async def update_run_status(
    db: AsyncSession,
    run_id: UUID,
    status: str,
    error: str | None = None,
) -> None:
    kwargs: dict[str, object] = {"status": status}
    if error is not None:
        kwargs["error_message"] = error
    if status == "completed":
        kwargs["completed_at"] = datetime.now(timezone.utc)
    await _update_run(db, run_id, **kwargs)


async def _increment_completed(db: AsyncSession, run_id: UUID) -> None:
    await db.execute(
        text("UPDATE runs SET completed_requests = completed_requests + 1 WHERE id = :id"),
        {"id": run_id},
    )
    await db.commit()


async def _increment_failed(db: AsyncSession, run_id: UUID) -> None:
    await db.execute(
        text("UPDATE runs SET failed_requests = failed_requests + 1 WHERE id = :id"),
        {"id": run_id},
    )
    await db.commit()


async def _record_error(
    db: AsyncSession,
    run_id: UUID,
    prompt_id: UUID,
    attempt: int,
    exc: Exception,
) -> None:
    """Persist a failed RequestRecord (status=error) to PostgreSQL."""
    record = RequestRecord(
        id=uuid4(),
        run_id=run_id,
        prompt_id=prompt_id,
        attempt=attempt,
        status="error",
        total_latency_ms=0.0,
        prompt_tokens=0,
        generated_tokens=0,
        error_type=type(exc).__name__,
        error_message=str(exc),
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()


# ---------------------------------------------------------------------------
# engine_watchdog
# ---------------------------------------------------------------------------

async def engine_watchdog(
    driver: InferenceEngineDriver,
    config: RunConfig,
    run_id: UUID,
) -> None:
    """Background task — raises RuntimeError if engine becomes unhealthy.

    Polls driver.is_healthy() every config.watchdog_interval_s seconds.
    Cancels the asyncio.gather in execute_run() the moment the engine dies,
    preventing all remaining prompts from burning through their retry budget
    against a dead engine.
    """
    while True:
        await asyncio.sleep(config.watchdog_interval_s)
        if not await driver.is_healthy(config):
            logger.error("Engine health check failed for run %s — failing run", run_id)
            raise RuntimeError("Engine became unhealthy during benchmark")


# ---------------------------------------------------------------------------
# execute_run
# ---------------------------------------------------------------------------

async def execute_run(
    run_id: UUID,
    config: RunConfig,
    suite: PromptSuite,
    db: AsyncSession,
) -> None:
    """Execute a benchmark run end-to-end.

    Phases:
    1. validate_config  — fail early if config is invalid
    2. spawn / attach   — engine via agent; wait_healthy; record PIDs
    3. ollama shim      — start Prometheus exporter if engine == "ollama"
    4. warmup           — discard results; sidecar NOT yet started
    5. sidecar          — start otelcol-contrib; stamp run_started_at
    6. benchmark        — gather run_one tasks + watchdog; write records

    Args:
        run_id:  UUID of the Run row (immutable, spine of all metrics).
        config:  Loaded RunConfig for this run.
        suite:   Loaded PromptSuite (prompts relationship not required on entry).
        db:      Async SQLAlchemy session for status updates.
    """
    driver = get_driver(config.engine)
    spawn_result: SpawnResult | None = None
    sidecar_proc: asyncio.subprocess.Process | None = None
    sidecar_config_path: Path | None = None
    ollama_shim: subprocess.Popen | None = None

    # Load prompts eagerly — avoids lazy-load MissingGreenlet inside gather tasks.
    sp_result = await db.execute(
        select(SuitePrompt)
        .where(SuitePrompt.suite_id == suite.id)
        .options(joinedload(SuitePrompt.prompt))
        .order_by(SuitePrompt.position)
    )
    suite_prompts = sp_result.scalars().all()
    prompts: list[Prompt] = [sp.prompt for sp in suite_prompts]

    if not prompts:
        raise ValueError(f"Suite {suite.id!r} has no prompts — cannot run benchmark")

    try:
        # ---- Phase 1: validate ------------------------------------------------
        errors = await driver.validate_config(config, db)
        if errors:
            raise ValueError(f"Invalid config: {'; '.join(errors)}")

        # ---- Phase 2: spawn / attach ------------------------------------------
        await update_run_status(db, run_id, "starting")
        spawn_result = await driver.spawn(config, run_id)
        await driver.wait_healthy(config, run_id)
        await _update_run(
            db,
            run_id,
            server_owned=spawn_result.owned,
            server_pid=spawn_result.pid,
            started_at=datetime.now(timezone.utc),
        )

        # ---- Phase 3: Ollama metrics shim (Ollama has no /metrics endpoint) ---
        if config.engine == "ollama":
            shim_path = Path(__file__).parent.parent / "drivers" / "ollama_shim.py"
            ollama_shim = subprocess.Popen(
                ["python", str(shim_path)],
                env={**os.environ, "RUN_ID": str(run_id), "MODEL_NAME": config.model},
            )

        # ---- Phase 4: warmup — sidecar NOT yet started -----------------------
        #     Metrics from warmup are excluded from Grafana; duration logged for UI.
        await update_run_status(db, run_id, "warming_up")
        warmup_start = time.perf_counter()
        for _ in range(config.warmup_rounds):
            async for _ in driver.stream_prompt(
                prompts[0].content, run_id="warmup", params=None
            ):
                pass  # consume and discard
        warmup_ms = (time.perf_counter() - warmup_start) * 1000
        await _update_run(db, run_id, warmup_duration_ms=warmup_ms)

        # ---- Phase 5: start OTel sidecar -------------------------------------
        #     run_started_at marks sidecar start — used for Grafana chart alignment.
        metrics_port = driver.get_metrics_port(config)
        sidecar_proc, sidecar_config_path = await start_sidecar(
            run_id=str(run_id),
            engine=config.engine,
            model=config.model,
            metrics_host=config.host,
            metrics_port=metrics_port,
            engine_host=config.host,
        )
        await _update_run(
            db,
            run_id,
            sidecar_pid=sidecar_proc.pid,
            run_started_at=datetime.now(timezone.utc),
        )

        # ---- Phase 6: benchmark suite with watchdog --------------------------
        await update_run_status(db, run_id, "running")
        semaphore = asyncio.Semaphore(config.concurrency)

        async def run_one(prompt: Prompt) -> None:
            async with semaphore:
                for attempt in range(1, config.auto_retry + 2):
                    try:
                        await collect_record(driver, config, prompt, run_id, attempt, db)
                        await _increment_completed(db, run_id)
                        return
                    except (
                        httpx.TimeoutException,
                        httpx.ConnectError,
                        httpx.RemoteProtocolError,
                        asyncio.TimeoutError,
                    ) as e:
                        # Transient — worth retrying with linear backoff
                        if attempt > config.auto_retry:
                            await _record_error(db, run_id, prompt.id, attempt, e)
                            await _increment_failed(db, run_id)
                            return
                        await asyncio.sleep(1 * attempt)
                    except Exception as e:
                        # Non-retryable (JSON decode, driver bug, etc.) — fail immediately
                        await _record_error(db, run_id, prompt.id, attempt, e)
                        await _increment_failed(db, run_id)
                        return

        watchdog_task = asyncio.create_task(engine_watchdog(driver, config, run_id))
        try:
            await asyncio.gather(*[run_one(p) for p in prompts], watchdog_task)
        except RuntimeError as e:
            if "unhealthy" in str(e):
                await update_run_status(
                    db,
                    run_id,
                    "failed",
                    error="Engine became unhealthy during benchmark",
                )
            raise
        finally:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except (asyncio.CancelledError, RuntimeError):
                pass  # expected — watchdog was cancelled or already raised

        await update_run_status(db, run_id, "completed")

    except asyncio.CancelledError:
        await update_run_status(db, run_id, "cancelled")
        raise  # falls through to finally — cleanup always runs

    except Exception as e:
        # Avoid double-write: RuntimeError from watchdog already set status above
        if not (isinstance(e, RuntimeError) and "unhealthy" in str(e)):
            await update_run_status(db, run_id, "failed", error=str(e))
        raise

    finally:
        # Cleanup order: shim → sidecar → engine (always runs, even on success)
        if ollama_shim:
            ollama_shim.terminate()
        if sidecar_proc:
            sidecar_proc.terminate()
            await sidecar_proc.wait()  # prevent zombie
        if sidecar_config_path:
            sidecar_config_path.unlink(missing_ok=True)  # S-04: delete temp config
        if spawn_result and spawn_result.owned:
            await driver.teardown(config, spawn_result)
        # spawn_result.owned=False → attach mode — leave engine running


# ---------------------------------------------------------------------------
# recover_stale_runs
# ---------------------------------------------------------------------------

async def recover_stale_runs() -> None:
    """Called once on backend startup. Marks in-progress runs as failed.

    Scans for runs stuck in starting/warming_up/running (left over from a
    crash or unclean shutdown). Attempts agent teardown for managed runs.
    Marks all stale runs failed with an appropriate error_message /
    cleanup_warning.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Run).where(Run.status.in_(["starting", "warming_up", "running"]))
        )
        stale_runs = result.scalars().all()

        for run in stale_runs:
            config = await db.get(RunConfig, run.config_id)
            if config is None:
                await _update_run(
                    db,
                    run.id,
                    status="failed",
                    error_message="Run was in-progress when backend restarted (config missing)",
                )
                continue

            agent_url = f"http://{config.host}:{config.agent_port}"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{agent_url}/run/{run.id}/status", timeout=5
                    )
                if resp.json().get("running"):
                    async with httpx.AsyncClient() as client:
                        await client.delete(f"{agent_url}/run/{run.id}", timeout=15)

                await _update_run(
                    db,
                    run.id,
                    status="failed",
                    error_message="Run was in-progress when backend restarted",
                )
            except Exception:
                await _update_run(
                    db,
                    run.id,
                    status="failed",
                    error_message="Run was in-progress when backend restarted",
                    cleanup_warning=(
                        "Agent unreachable during recovery — engine may still be running"
                    ),
                )

        if stale_runs:
            logger.warning("Recovered %d stale runs on startup", len(stale_runs))
