from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Project, Run, RunConfig
from schemas.project import ProjectCreate, ProjectRead
from schemas.run import RunSummary

router = APIRouter(prefix="/api/projects", tags=["projects"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def list_projects(db: DbDep) -> dict:
    result = await db.execute(select(Project).order_by(Project.created_at))
    projects = result.scalars().all()
    return {"items": [ProjectRead.model_validate(p) for p in projects]}


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, db: DbDep) -> ProjectRead:
    project = Project(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/{project_id}/runs")
async def list_project_runs(project_id: uuid.UUID, db: DbDep) -> dict:
    """Return all runs whose RunConfig has project_id == project_id."""
    stmt = (
        select(Run, RunConfig)
        .join(RunConfig, Run.config_id == RunConfig.id)
        .where(RunConfig.project_id == project_id)
        .order_by(Run.started_at.desc().nullslast())
    )
    result = await db.execute(stmt)
    rows = result.all()

    items = [
        RunSummary(
            id=run.id,
            config_id=run.config_id,
            status=run.status,
            total_requests=run.total_requests,
            completed_requests=run.completed_requests,
            failed_requests=run.failed_requests,
            started_at=run.started_at,
            completed_at=run.completed_at,
            engine=config.engine,
            model=config.model,
            host=config.host,
        )
        for run, config in rows
    ]
    return {"items": items}
