from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ComparisonRequest(BaseModel):
    run_ids: list[UUID]
    metric: str = "p99"  # "p99" | "ttft" | "throughput"


class RunStats(BaseModel):
    run_id: UUID
    engine: str
    model: str
    # Latency stats (ms)
    avg_latency_ms: float | None
    p50_latency_ms: float | None
    p99_latency_ms: float | None
    min_latency_ms: float | None
    max_latency_ms: float | None
    stddev_latency_ms: float | None
    # TTFT stats (ms)
    avg_ttft_ms: float | None
    p50_ttft_ms: float | None
    p99_ttft_ms: float | None
    # Throughput
    avg_tokens_per_sec: float | None
    # Request counts
    total_requests: int
    failed_requests: int
    sample_count: int


class ComparisonResult(BaseModel):
    runs: list[RunStats]


# ---------------------------------------------------------------------------
# Saved comparisons
# ---------------------------------------------------------------------------

class SavedComparisonCreate(BaseModel):
    name: str
    run_ids: list[UUID]
    description: str | None = None
    metric: str = "p99"


class SavedComparisonRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    run_ids: list
    metric: str
    created_at: datetime
    share_token: str

    model_config = {"from_attributes": True}
