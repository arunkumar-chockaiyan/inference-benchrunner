from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}
