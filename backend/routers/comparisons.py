"""
FastAPI router for /api/comparisons — saved comparison management.

Endpoints:
  GET  /api/comparisons          — list all saved comparisons
  POST /api/comparisons          — create a new saved comparison
  GET  /api/comparisons/{token}  — load by share token (string, not UUID)
"""
from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import SavedComparison
from schemas.comparison import SavedComparisonCreate, SavedComparisonRead

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# GET /api/comparisons
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
async def list_comparisons(db: DbDep) -> dict:
    """Return all saved comparisons ordered by creation time (newest first)."""
    result = await db.execute(
        select(SavedComparison).order_by(SavedComparison.created_at.desc())
    )
    comparisons = result.scalars().all()
    items = [SavedComparisonRead.model_validate(c) for c in comparisons]
    return {"items": [i.model_dump() for i in items]}


# ---------------------------------------------------------------------------
# POST /api/comparisons
# ---------------------------------------------------------------------------

@router.post("", response_model=SavedComparisonRead, status_code=201)
async def create_comparison(body: SavedComparisonCreate, db: DbDep) -> SavedComparisonRead:
    """Persist a named comparison with an auto-generated share token."""
    comparison = SavedComparison(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        run_ids=[str(rid) for rid in body.run_ids],
        metric=body.metric,
        share_token=secrets.token_urlsafe(16),
    )
    db.add(comparison)
    await db.commit()
    await db.refresh(comparison)
    return SavedComparisonRead.model_validate(comparison)


# ---------------------------------------------------------------------------
# GET /api/comparisons/{token}
# ---------------------------------------------------------------------------

@router.get("/{token}", response_model=SavedComparisonRead)
async def get_comparison_by_token(token: str, db: DbDep) -> SavedComparisonRead:
    """Load a saved comparison by its share token."""
    result = await db.execute(
        select(SavedComparison).where(SavedComparison.share_token == token)
    )
    comparison = result.scalar_one_or_none()
    if comparison is None:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return SavedComparisonRead.model_validate(comparison)
