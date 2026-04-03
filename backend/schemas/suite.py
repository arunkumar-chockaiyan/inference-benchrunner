from __future__ import annotations
from uuid import UUID
from pydantic import BaseModel


class SuiteCreate(BaseModel):
    name: str
    description: str | None = None
    prompt_ids: list[UUID]


class SuiteRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    prompt_ids: list[UUID]

    model_config = {"from_attributes": True}
