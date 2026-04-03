from __future__ import annotations
from uuid import UUID
from pydantic import BaseModel


class EngineModelRead(BaseModel):
    id: UUID
    engine: str
    model_id: str
    display_name: str | None
    is_available: bool

    model_config = {"from_attributes": True}
