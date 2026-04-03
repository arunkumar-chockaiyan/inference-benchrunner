from __future__ import annotations
from uuid import UUID
from pydantic import BaseModel


class ComparisonRequest(BaseModel):
    run_ids: list[UUID]


class RunStats(BaseModel):
    run_id: UUID
    engine: str
    model: str
    p50_ttft_ms: float | None
    p95_ttft_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    tokens_per_sec: float | None
    total_requests: int
    failed_requests: int


class ComparisonResult(BaseModel):
    runs: list[RunStats]
