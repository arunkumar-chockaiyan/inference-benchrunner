from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Prompt
from schemas.prompt import PromptCreate, PromptRead, PromptUpdate

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Import / export — MUST be registered before /{id} routes
# ---------------------------------------------------------------------------

@router.post("/import")
async def import_prompts(
    body: dict,
    db: DbDep,
) -> dict:
    """Bulk-import prompts from a JSON body: {"prompts": [PromptCreate]}."""
    raw_prompts: list[dict] = body.get("prompts", [])
    rows = [
        Prompt(
            id=uuid.uuid4(),
            name=p["name"],
            content=p["content"],
            category=p.get("category", "short"),
            variables=p.get("variables", {}),
        )
        for p in raw_prompts
    ]
    db.add_all(rows)
    await db.commit()
    return {"imported": len(rows)}


@router.get("/export")
async def export_prompts(db: DbDep) -> dict:
    """Export all prompts as JSON."""
    result = await db.execute(select(Prompt).order_by(Prompt.created_at))
    prompts = result.scalars().all()
    return {"prompts": [PromptRead.model_validate(p) for p in prompts]}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def list_prompts(
    db: DbDep,
    category: str | None = Query(default=None),
    cursor: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List prompts with optional category filter and cursor-based pagination."""
    stmt = select(Prompt)
    if category is not None:
        stmt = stmt.where(Prompt.category == category)
    if cursor is not None:
        stmt = stmt.where(Prompt.id > cursor)
    stmt = stmt.order_by(Prompt.id).limit(limit)

    result = await db.execute(stmt)
    items = result.scalars().all()

    next_cursor: uuid.UUID | None = None
    if len(items) == limit:
        next_cursor = items[-1].id

    return {
        "items": [PromptRead.model_validate(p) for p in items],
        "next_cursor": next_cursor,
    }


@router.post("", status_code=201)
async def create_prompt(body: PromptCreate, db: DbDep) -> PromptRead:
    prompt = Prompt(
        id=uuid.uuid4(),
        name=body.name,
        content=body.content,
        category=body.category,
        variables=body.variables,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return PromptRead.model_validate(prompt)


@router.get("/{prompt_id}")
async def get_prompt(prompt_id: uuid.UUID, db: DbDep) -> PromptRead:
    prompt = await db.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="not found")
    return PromptRead.model_validate(prompt)


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: uuid.UUID, body: PromptUpdate, db: DbDep
) -> PromptRead:
    prompt = await db.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="not found")

    if body.name is not None:
        prompt.name = body.name
    if body.content is not None:
        prompt.content = body.content
    if body.category is not None:
        prompt.category = body.category
    if body.variables is not None:
        prompt.variables = body.variables

    await db.commit()
    await db.refresh(prompt)
    return PromptRead.model_validate(prompt)


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(prompt_id: uuid.UUID, db: DbDep) -> None:
    prompt = await db.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(prompt)
    await db.commit()
