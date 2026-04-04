from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PromptCreate(BaseModel):
    name: str
    content: str
    category: str = "short"  # short|long|code|rag|multi_turn
    variables: dict[str, str] = {}


class PromptUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    category: str | None = None
    variables: dict[str, str] | None = None


class PromptRead(BaseModel):
    id: UUID
    name: str
    content: str
    category: str
    variables: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
