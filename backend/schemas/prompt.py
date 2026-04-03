from __future__ import annotations
from uuid import UUID
from pydantic import BaseModel


class PromptCreate(BaseModel):
    text: str
    tags: list[str] | None = None


class PromptRead(BaseModel):
    id: UUID
    text: str
    tags: list[str] | None

    model_config = {"from_attributes": True}
