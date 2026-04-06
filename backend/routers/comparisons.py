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
from models import SavedComparison, Run
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
    """Persist a named comparison with an auto-generated share token.

    Validation: All run_ids must use the same PromptSuite (apples-to-apples comparison).
    This ensures the comparison is meaningful — same workload across different configs.
    """
    if not body.run_ids:
        raise HTTPException(status_code=422, detail="run_ids list cannot be empty")

    # Fetch all runs and validate they share the same suite_id
    result = await db.execute(
        select(Run).where(Run.id.in_(body.run_ids))
    )
    runs = result.scalars().all()

    if len(runs) != len(body.run_ids):
        missing_ids = set(body.run_ids) - {r.id for r in runs}
        raise HTTPException(
            status_code=404,
            detail=f"Some run_ids not found: {missing_ids}"
        )

    # Validate all runs use the same suite
    suite_ids = {r.config.suite_id for r in runs}
    if len(suite_ids) > 1:
        raise HTTPException(
            status_code=422,
            detail=f"All runs must use the same PromptSuite. Found {len(suite_ids)} different suites: {suite_ids}"
        )

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
