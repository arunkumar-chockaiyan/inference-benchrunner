from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import PromptSuite, SuitePrompt
from schemas.suite import SuiteCreate, SuiteRead, SuiteUpdate

router = APIRouter(prefix="/api/suites", tags=["suites"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _build_suite_read(suite: PromptSuite, db: AsyncSession) -> SuiteRead:
    """Fetch ordered prompt_ids for a suite and return a SuiteRead."""
    result = await db.execute(
        select(SuitePrompt)
        .where(SuitePrompt.suite_id == suite.id)
        .order_by(SuitePrompt.position)
    )
    entries = result.scalars().all()
    return SuiteRead(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        version=suite.version,
        prompt_ids=[e.prompt_id for e in entries],
        created_at=suite.created_at,
        updated_at=suite.updated_at,
    )


@router.get("")
async def list_suites(db: DbDep) -> dict:
    result = await db.execute(select(PromptSuite).order_by(PromptSuite.created_at))
    suites = result.scalars().all()
    items = [await _build_suite_read(s, db) for s in suites]
    return {"items": items}


@router.post("", status_code=201)
async def create_suite(body: SuiteCreate, db: DbDep) -> SuiteRead:
    suite = PromptSuite(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        version=1,
    )
    db.add(suite)
    await db.flush()  # populate suite.id before inserting SuitePrompt rows

    for position, prompt_id in enumerate(body.prompt_ids):
        db.add(SuitePrompt(suite_id=suite.id, prompt_id=prompt_id, position=position))

    await db.commit()
    await db.refresh(suite)
    return await _build_suite_read(suite, db)


@router.get("/{suite_id}")
async def get_suite(suite_id: uuid.UUID, db: DbDep) -> SuiteRead:
    suite = await db.get(PromptSuite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="not found")
    return await _build_suite_read(suite, db)


@router.put("/{suite_id}")
async def update_suite(
    suite_id: uuid.UUID, body: SuiteUpdate, db: DbDep
) -> SuiteRead:
    suite = await db.get(PromptSuite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="not found")

    if body.name is not None:
        suite.name = body.name
    if body.description is not None:
        suite.description = body.description

    if body.prompt_ids is not None:
        # Delete all existing SuitePrompt rows then insert the new set
        await db.execute(
            sa_delete(SuitePrompt).where(SuitePrompt.suite_id == suite_id)
        )
        for position, prompt_id in enumerate(body.prompt_ids):
            db.add(SuitePrompt(suite_id=suite_id, prompt_id=prompt_id, position=position))
        suite.version += 1

    await db.commit()
    await db.refresh(suite)
    return await _build_suite_read(suite, db)


@router.delete("/{suite_id}", status_code=204)
async def delete_suite(suite_id: uuid.UUID, db: DbDep) -> None:
    suite = await db.get(PromptSuite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(suite)
    await db.commit()
