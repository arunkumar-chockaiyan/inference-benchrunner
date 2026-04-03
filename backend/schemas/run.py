from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class RunCreate(BaseModel):
    engine: str
    model: str
    host: str
    port: int
    suite_id: UUID | None = None
    prompt_ids: list[UUID] | None = None
    spawn_mode: str = "managed"
    parameters: dict | None = None


class RunRead(BaseModel):
    id: UUID
    engine: str
    model: str
    host: str
    port: int
    status: str
    spawn_mode: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class RunSummary(BaseModel):
    id: UUID
    engine: str
    model: str
    status: str
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
