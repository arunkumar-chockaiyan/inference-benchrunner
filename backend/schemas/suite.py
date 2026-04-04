from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SuiteCreate(BaseModel):
    name: str
    description: str = ""
    prompt_ids: list[UUID]  # ordered; maps to SuitePrompt.position


class SuiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt_ids: list[UUID] | None = None  # replaces existing list; auto-increments version


class SuiteRead(BaseModel):
    id: UUID
    name: str
    description: str
    version: int
    prompt_ids: list[UUID]  # ordered by position
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
