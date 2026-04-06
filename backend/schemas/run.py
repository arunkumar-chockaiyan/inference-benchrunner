from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# RunConfig schema (embedded in RunRead; used by create)
# ---------------------------------------------------------------------------

class RunConfigRead(BaseModel):
    id: UUID
    name: str
    engine: str
    model: str
    host: str
    port: int
    agent_port: int
    spawn_mode: str
    concurrency: int
    temperature: float
    max_tokens: int
    top_p: float
    request_timeout_s: int
    warmup_rounds: int
    auto_retry: int
    variable_overrides: dict
    notes: str
    tags: list

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Run creation — creates a RunConfig + Run atomically
# ---------------------------------------------------------------------------

class RunCreate(BaseModel):
    # RunConfig fields
    name: str
    engine: str
    model: str
    suite_id: UUID
    host: str = "localhost"
    port: int
    agent_port: int = 8787
    spawn_mode: str = "attach"       # "managed" | "attach"
    health_timeout_s: int = 180
    concurrency: int = 1
    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 1.0
    request_timeout_s: int = 120
    watchdog_interval_s: int = 10
    warmup_rounds: int = 3
    auto_retry: int = 2
    variable_overrides: dict[str, str] = {}
    notes: str = ""
    tags: list[str] = []
    project_id: UUID | None = None


# ---------------------------------------------------------------------------
# Run read schemas
# ---------------------------------------------------------------------------

class RunRead(BaseModel):
    id: UUID
    config_id: UUID
    status: str
    total_requests: int
    completed_requests: int
    failed_requests: int
    started_at: datetime | None
    warmup_duration_ms: float | None
    run_started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    server_owned: bool
    server_pid: int | None
    sidecar_pid: int | None
    cleanup_warning: str | None
    config: RunConfigRead

    model_config = {"from_attributes": True}


class RunSummary(BaseModel):
    """Lightweight shape for list pages."""
    id: UUID
    config_id: UUID
    status: str
    total_requests: int
    completed_requests: int
    failed_requests: int
    started_at: datetime | None
    completed_at: datetime | None
    # Denormalized from config for list display
    engine: str
    model: str
    host: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# InferenceRecord read schema
# ---------------------------------------------------------------------------

class InferenceRecordRead(BaseModel):
    id: UUID
    run_id: UUID
    prompt_id: UUID
    attempt: int
    status: str
    ttft_ms: float | None
    total_latency_ms: float
    prompt_tokens: int
    generated_tokens: int
    tokens_per_second: float | None
    error_type: str | None
    error_message: str | None
    started_at: datetime

    model_config = {"from_attributes": True}
