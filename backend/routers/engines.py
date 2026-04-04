from __future__ import annotations

import logging
import time
import types
import uuid
from datetime import datetime, timezone

import httpx
import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from drivers import DRIVERS, get_driver
from models import EngineModel
from schemas.engine import (
    EngineModelCreate,
    EngineModelRead,
    EngineMeta,
    ProbeRequest,
    ProbeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engines")

_VALID_ENGINES = frozenset(DRIVERS.keys())

_ENGINE_META: list[EngineMeta] = [
    EngineMeta(name="ollama", display_name="Ollama", spawn_modes=["attach"], default_port=11434),
    EngineMeta(
        name="llamacpp",
        display_name="llama.cpp server",
        spawn_modes=["managed", "attach"],
        default_port=8080,
    ),
    EngineMeta(
        name="vllm",
        display_name="vLLM",
        spawn_modes=["managed", "attach"],
        default_port=8000,
    ),
    EngineMeta(
        name="sglang",
        display_name="SGLang",
        spawn_modes=["managed", "attach"],
        default_port=30000,
    ),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _check_engine(engine: str) -> None:
    if engine not in _VALID_ENGINES:
        raise HTTPException(status_code=400, detail=f"Unknown engine {engine!r}. Valid: {sorted(_VALID_ENGINES)}")


# ---------------------------------------------------------------------------
# GET /api/engines
# ---------------------------------------------------------------------------

@router.get("")
async def list_engines() -> dict:
    return {"engines": [m.model_dump() for m in _ENGINE_META]}


# ---------------------------------------------------------------------------
# POST /api/engines/probe  — must be registered BEFORE /{engine}/models
# ---------------------------------------------------------------------------

@router.post("/probe", response_model=ProbeResponse)
async def probe_engine(body: ProbeRequest) -> ProbeResponse:
    health_path = "/api/tags" if body.engine == "ollama" else "/health"
    url = f"http://{body.host}:{body.port}{health_path}"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        latency_ms = (time.perf_counter() - t0) * 1000
        if resp.is_success:
            return ProbeResponse(reachable=True, latency_ms=round(latency_ms, 2), error=None)
        return ProbeResponse(
            reachable=False,
            latency_ms=round(latency_ms, 2),
            error=f"HTTP {resp.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        return ProbeResponse(reachable=False, latency_ms=None, error=str(exc))


# ---------------------------------------------------------------------------
# GET /api/engines/{engine}/models
# ---------------------------------------------------------------------------

@router.get("/{engine}/models")
async def list_engine_models(
    engine: str,
    host: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_engine(engine)
    stmt = select(EngineModel).where(EngineModel.engine == engine)
    if host is not None:
        stmt = stmt.where(EngineModel.host == host)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"items": [EngineModelRead.model_validate(r) for r in rows]}


# ---------------------------------------------------------------------------
# POST /api/engines/{engine}/models/sync
# ---------------------------------------------------------------------------

@router.post("/{engine}/models/sync")
async def sync_engine_models(
    engine: str,
    host: str,
    port: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_engine(engine)

    if engine == "llamacpp":
        return {"synced": 0, "message": "llamacpp does not support model listing"}

    driver = get_driver(engine)
    config_stub = types.SimpleNamespace(host=host, port=port)

    try:
        fetched: list[dict] = await driver.list_models(config_stub)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"engine unreachable: {exc}") from exc

    fetched_model_ids: set[str] = set()
    synced_count = 0
    now = _utcnow()

    for item in fetched:
        model_id: str = item["model_id"]
        display_name: str = item.get("display_name", model_id)
        fetched_model_ids.add(model_id)

        existing_stmt = select(EngineModel).where(
            EngineModel.engine == engine,
            EngineModel.host == host,
            EngineModel.model_id == model_id,
        )
        result = await db.execute(existing_stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.display_name = display_name
            existing.last_synced = now
            existing.is_stale = False
            existing.source = "synced"
        else:
            db.add(
                EngineModel(
                    id=uuid.uuid4(),
                    engine=engine,
                    host=host,
                    model_id=model_id,
                    display_name=display_name,
                    source="synced",
                    last_synced=now,
                    is_stale=False,
                    notes="",
                )
            )
        synced_count += 1

    # Mark synced rows absent from this sync as stale (never touch manual rows)
    if fetched_model_ids:
        stale_stmt = (
            sa_update(EngineModel)
            .where(
                EngineModel.engine == engine,
                EngineModel.host == host,
                EngineModel.source == "synced",
                EngineModel.model_id.not_in(fetched_model_ids),
            )
            .values(is_stale=True)
        )
    else:
        # All existing synced rows for this engine+host become stale
        stale_stmt = (
            sa_update(EngineModel)
            .where(
                EngineModel.engine == engine,
                EngineModel.host == host,
                EngineModel.source == "synced",
            )
            .values(is_stale=True)
        )

    await db.execute(stale_stmt)
    await db.commit()

    return {"synced": synced_count}


# ---------------------------------------------------------------------------
# POST /api/engines/{engine}/models  — manual add
# ---------------------------------------------------------------------------

@router.post("/{engine}/models", status_code=201, response_model=EngineModelRead)
async def add_engine_model(
    engine: str,
    body: EngineModelCreate,
    db: AsyncSession = Depends(get_db),
) -> EngineModelRead:
    _check_engine(engine)

    row = EngineModel(
        id=uuid.uuid4(),
        engine=engine,
        host=body.host,
        model_id=body.model_id,
        display_name=body.display_name or body.model_id,
        source="manual",
        last_synced=None,
        is_stale=False,
        notes=body.notes,
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Model {body.model_id!r} already exists for engine={engine} host={body.host}",
        )

    return EngineModelRead.model_validate(row)


# ---------------------------------------------------------------------------
# DELETE /api/engines/{engine}/models/{model_id}
# ---------------------------------------------------------------------------

@router.delete("/{engine}/models/{model_id}", status_code=204)
async def delete_engine_model(
    engine: str,
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    _check_engine(engine)

    result = await db.execute(
        select(EngineModel).where(
            EngineModel.id == model_id,
            EngineModel.engine == engine,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"EngineModel {model_id} not found")

    await db.delete(row)
    await db.commit()
