"""
FastAPI router for /api/runs and WebSocket /ws/runs/{id}.

Route registration order matters:
  POST /api/runs/compare  — registered BEFORE /{id} to avoid literal "compare"
                            being matched as a UUID path parameter.

Two routers are exported:
  router    — prefix="/api/runs"  (HTTP endpoints)
  ws_router — no prefix           (WebSocket endpoint /ws/runs/{id})
Both are included by main.py.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from statistics import mean, stdev
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import AsyncSessionLocal, get_db
from drivers import get_driver
from models import InferenceRecord, Run, RunConfig, PromptSuite, SuitePromptMap
from schemas.comparison import ComparisonRequest, ComparisonResult, RunStats
from schemas.run import InferenceRecordRead, RunCreate, RunRead, RunConfigRead, RunSummary
from services.runner import execute_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])
ws_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]

# Module-level task registry: run_id → asyncio.Task
_run_tasks: dict[UUID, asyncio.Task] = {}

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------

async def _run_background(run_id: UUID) -> None:
    """Execute a run in a background asyncio task with its own DB session."""
    async with AsyncSessionLocal() as db:
        run = await db.get(Run, run_id)
        if run is None:
            logger.error("_run_background: run %s not found", run_id)
            return
        config = await db.get(RunConfig, run.config_id)
        if config is None:
            logger.error("_run_background: config for run %s not found", run_id)
            return
        suite = await db.get(PromptSuite, config.suite_id)
        if suite is None:
            logger.error("_run_background: suite for run %s not found", run_id)
            return
        try:
            await execute_run(run_id, config, suite, db)
        except Exception:
            # execute_run already marks the run failed; swallow here so the task
            # finishes cleanly and the done-callback can remove it from the registry.
            pass


# ---------------------------------------------------------------------------
# Stats helper — pure Python (no SQL percentile functions)
# ---------------------------------------------------------------------------

def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Return the value at the given percentile (0–1) from a pre-sorted list."""
    if not sorted_values:
        return None
    idx = int(len(sorted_values) * pct)
    # Clamp to last valid index
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]


def _compute_stats(values: list[float]) -> tuple[
    float | None, float | None, float | None, float | None, float | None, float | None
]:
    """Return (avg, p50, p99, min, max, stddev) from a list of floats."""
    if not values:
        return None, None, None, None, None, None
    s = sorted(values)
    avg = mean(s)
    p50 = _percentile(s, 0.50)
    p99 = _percentile(s, 0.99)
    lo = s[0]
    hi = s[-1]
    sd = stdev(s) if len(s) > 1 else None
    return avg, p50, p99, lo, hi, sd


# ---------------------------------------------------------------------------
# POST /api/runs/compare  — MUST come before /{id}
# ---------------------------------------------------------------------------

@router.post("/compare", response_model=ComparisonResult)
async def compare_runs(body: ComparisonRequest, db: DbDep) -> ComparisonResult:
    """Compute per-run statistics for a set of run IDs."""
    run_stats: list[RunStats] = []

    for run_id in body.run_ids:
        run = await db.get(Run, run_id, options=[joinedload(Run.config)])
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        config: RunConfig = run.config

        # Load successful InferenceRecords for this run
        result = await db.execute(
            select(InferenceRecord)
            .where(InferenceRecord.run_id == run_id)
            .where(InferenceRecord.status == "success")
        )
        records = result.scalars().all()

        if records:
            latencies = [r.total_latency_ms for r in records]
            ttfts = [r.ttft_ms for r in records if r.ttft_ms is not None]
            tps_values = [r.tokens_per_second for r in records if r.tokens_per_second is not None]

            avg_lat, p50_lat, p99_lat, min_lat, max_lat, sd_lat = _compute_stats(latencies)
            avg_ttft, p50_ttft, p99_ttft, _, _, _ = _compute_stats(ttfts)
            avg_tps = mean(tps_values) if tps_values else None
            sample_count = len(records)
        else:
            avg_lat = p50_lat = p99_lat = min_lat = max_lat = sd_lat = None
            avg_ttft = p50_ttft = p99_ttft = None
            avg_tps = None
            sample_count = 0

        run_stats.append(
            RunStats(
                run_id=run.id,
                engine=config.engine,
                model=config.model,
                avg_latency_ms=avg_lat,
                p50_latency_ms=p50_lat,
                p99_latency_ms=p99_lat,
                min_latency_ms=min_lat,
                max_latency_ms=max_lat,
                stddev_latency_ms=sd_lat,
                avg_ttft_ms=avg_ttft,
                p50_ttft_ms=p50_ttft,
                p99_ttft_ms=p99_ttft,
                avg_tokens_per_sec=avg_tps,
                total_requests=run.total_requests,
                failed_requests=run.failed_requests,
                sample_count=sample_count,
            )
        )

    return ComparisonResult(runs=run_stats)


# ---------------------------------------------------------------------------
# GET /api/runs
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
async def list_runs(
    db: DbDep,
    status: str | None = Query(default=None),
    engine: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    cursor: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List runs with optional filters. Returns cursor-paginated results."""
    stmt = (
        select(Run)
        .join(RunConfig, Run.config_id == RunConfig.id)
        .options(joinedload(Run.config))
        .order_by(Run.id)
    )

    if status is not None:
        stmt = stmt.where(Run.status == status)
    if engine is not None:
        stmt = stmt.where(RunConfig.engine == engine)
    if cursor is not None:
        stmt = stmt.where(Run.id > cursor)

    # Fetch limit+1 to detect whether a next page exists
    stmt = stmt.limit(limit + 1)

    result = await db.execute(stmt)
    runs = list(result.scalars().all())

    # Python-side tag filter (tags stored as JSON array)
    if tag is not None:
        runs = [r for r in runs if tag in (r.config.tags or [])]

    has_next = len(runs) > limit
    page = runs[:limit]

    next_cursor = page[-1].id if has_next else None

    items = [
        RunSummary(
            id=r.id,
            config_id=r.config_id,
            status=r.status,
            total_requests=r.total_requests,
            completed_requests=r.completed_requests,
            failed_requests=r.failed_requests,
            started_at=r.started_at,
            completed_at=r.completed_at,
            engine=r.config.engine,
            model=r.config.model,
            host=r.config.host,
        )
        for r in page
    ]

    return {"items": [i.model_dump() for i in items], "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# POST /api/runs
# ---------------------------------------------------------------------------

@router.post("", response_model=RunRead, status_code=201)
async def create_run(body: RunCreate, db: DbDep) -> RunRead:
    """Create RunConfig + Run atomically, then launch run as a background task."""
    # Verify suite exists and count prompts
    suite = await db.get(PromptSuite, body.suite_id)
    if suite is None:
        raise HTTPException(status_code=422, detail=f"Suite {body.suite_id} not found")

    suite_prompt_result = await db.execute(
        select(SuitePromptMap).where(SuitePromptMap.suite_id == body.suite_id)
    )
    prompt_count = len(suite_prompt_result.scalars().all())

    # Build RunConfig
    config = RunConfig(
        id=uuid.uuid4(),
        name=body.name,
        engine=body.engine,
        model=body.model,
        suite_id=body.suite_id,
        host=body.host,
        port=body.port,
        agent_port=body.agent_port,
        spawn_mode=body.spawn_mode,
        health_timeout_s=body.health_timeout_s,
        concurrency=body.concurrency,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        top_p=body.top_p,
        request_timeout_s=body.request_timeout_s,
        watchdog_interval_s=body.watchdog_interval_s,
        warmup_rounds=body.warmup_rounds,
        auto_retry=body.auto_retry,
        variable_overrides=body.variable_overrides,
        notes=body.notes,
        tags=body.tags,
        project_id=body.project_id,
    )
    db.add(config)
    await db.flush()  # assigns config.id without committing

    # Snapshot the config as a plain dict for the run record
    config_snapshot = {
        col.key: getattr(config, col.key)
        for col in RunConfig.__table__.columns
        if col.key not in ("id",)
    }
    # Coerce non-serialisable types (UUID, datetime) to strings
    config_snapshot = {
        k: str(v) if isinstance(v, (uuid.UUID, datetime)) else v
        for k, v in config_snapshot.items()
    }

    run = Run(
        id=uuid.uuid4(),
        config_id=config.id,
        config_snapshot=config_snapshot,
        status="pending",
        total_requests=prompt_count,
    )
    db.add(run)
    await db.commit()

    # Reload with eager config for the response
    run = await db.get(Run, run.id, options=[joinedload(Run.config)])

    # Launch background task
    task = asyncio.create_task(_run_background(run.id))
    _run_tasks[run.id] = task
    task.add_done_callback(lambda t: _run_tasks.pop(run.id, None))

    return RunRead.model_validate(run)


# ---------------------------------------------------------------------------
# GET /api/runs/{id}
# ---------------------------------------------------------------------------

@router.get("/{run_id}", response_model=RunRead)
async def get_run(run_id: UUID, db: DbDep) -> RunRead:
    """Return a single run with its config."""
    run = await db.get(Run, run_id, options=[joinedload(Run.config)])
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunRead.model_validate(run)


# ---------------------------------------------------------------------------
# DELETE /api/runs/{id}
# ---------------------------------------------------------------------------

@router.delete("/{run_id}", status_code=204)
async def cancel_run(run_id: UUID, db: DbDep) -> None:
    """Cancel an in-progress run. 409 if already in a terminal state."""
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Run is already in terminal state: {run.status}",
        )

    task = _run_tasks.get(run_id)
    if task is not None:
        task.cancel()

    run.status = "cancelled"
    await db.commit()


# ---------------------------------------------------------------------------
# GET /api/runs/{id}/requests
# ---------------------------------------------------------------------------

@router.get("/{run_id}/requests", response_model=dict)
async def list_run_requests(
    run_id: UUID,
    db: DbDep,
    cursor: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Return paginated InferenceRecords for a run."""
    # Verify run exists
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    stmt = (
        select(InferenceRecord)
        .where(InferenceRecord.run_id == run_id)
        .order_by(InferenceRecord.id)
    )
    if cursor is not None:
        stmt = stmt.where(InferenceRecord.id > cursor)
    stmt = stmt.limit(limit + 1)

    result = await db.execute(stmt)
    records = list(result.scalars().all())

    has_next = len(records) > limit
    page = records[:limit]
    next_cursor = page[-1].id if has_next else None

    items = [InferenceRecordRead.model_validate(r) for r in page]
    return {"items": [i.model_dump() for i in items], "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# WS /ws/runs/{run_id}
# ---------------------------------------------------------------------------

@ws_router.websocket("/ws/runs/{run_id}")
async def run_ws(
    websocket: WebSocket,
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Stream live run progress events every 2 seconds until terminal state."""
    await websocket.accept()

    # Initial existence check
    run = await db.get(Run, run_id, options=[joinedload(Run.config)])
    if run is None:
        await websocket.send_json({"detail": "run not found"})
        await websocket.close(code=1008)
        return

    try:
        while True:
            # Reload run state on each tick
            await db.refresh(run)

            # Compute timing fields
            now = datetime.now(timezone.utc)
            if run.run_started_at:
                elapsed = (now - run.run_started_at).total_seconds()
            else:
                elapsed = 0.0

            if run.completed_requests > 0 and run.run_started_at:
                remaining = run.total_requests - run.completed_requests
                eta: float | None = elapsed * remaining / run.completed_requests
            else:
                eta = None

            # Current TPS: avg tokens_per_second from the last 10 records
            tps_result = await db.execute(
                select(InferenceRecord.tokens_per_second)
                .where(InferenceRecord.run_id == run_id)
                .where(InferenceRecord.tokens_per_second.is_not(None))
                .order_by(InferenceRecord.started_at.desc())
                .limit(10)
            )
            recent_tps = [row[0] for row in tps_result.all()]
            current_tps: float | None = mean(recent_tps) if recent_tps else None

            # Server liveness — swallow any exception
            server_alive = False
            try:
                config = run.config
                driver = get_driver(config.engine)
                server_alive = await driver.is_healthy(config)
            except Exception:
                server_alive = False

            event = {
                "run_id": str(run.id),
                "status": run.status,
                "completed": run.completed_requests,
                "total": run.total_requests,
                "failed": run.failed_requests,
                "current_tps": current_tps,
                "elapsed_seconds": elapsed,
                "eta_seconds": eta,
                "server_alive": server_alive,
            }
            await websocket.send_json(event)

            if run.status in _TERMINAL_STATUSES:
                await websocket.close(code=1000)
                return

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        return
