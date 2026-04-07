from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EngineModelRead(BaseModel):
    id: UUID
    engine: str
    model_id: str
    display_name: str
    source: str         # "synced" | "manual"
    is_stale: bool
    last_synced: datetime | None
    notes: str

    model_config = {"from_attributes": True}


class EngineModelCreate(BaseModel):
    """For manual model registry entries."""
    engine: str
    model_id: str
    display_name: str = ""
    notes: str = ""


class EngineMeta(BaseModel):
    """Static metadata about a supported engine."""
    name: str           # "ollama" | "llamacpp" | "vllm" | "sglang"
    display_name: str
    spawn_modes: list[str]   # which spawn_modes are valid for this engine
    default_port: int


class ProbeRequest(BaseModel):
    host: str
    port: int
    engine: str


class ProbeResponse(BaseModel):
    reachable: bool
    latency_ms: float | None
    error: str | None
