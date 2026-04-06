"""
Request record collection service.

Owns collect_record() — consumes a stream_prompt() AsyncIterator,
builds a InferenceRecord, writes to PostgreSQL, and best-effort writes
to ClickHouse via clickhouse.ch_insert().
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from drivers.base import InferenceEngineDriver, PromptParams, ResponseMeta
from models import Prompt, InferenceRecord, RunConfig
from services.clickhouse import ch_insert

logger = logging.getLogger(__name__)


def render_prompt(prompt: Prompt, overrides: dict[str, str] | None) -> str:
    """Replace {{key}} placeholders in prompt.content with variable values.

    prompt.variables provides defaults; overrides take precedence.
    Keys not present in either dict are left as-is in the rendered text.
    """
    variables = {**(prompt.variables or {}), **(overrides or {})}
    text = prompt.content
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


async def collect_record(
    driver: InferenceEngineDriver,
    config: RunConfig,
    prompt: Prompt,
    run_id: UUID,
    attempt: int,
    db: AsyncSession,
) -> InferenceRecord:
    """Stream one prompt, measure latency/TTFT, write to PostgreSQL + ClickHouse.

    Returns the InferenceRecord already committed to PostgreSQL.
    ClickHouse write is best-effort — failure is logged but never raised.

    Args:
        driver:   Active engine driver for this run.
        config:   RunConfig providing inference parameters and engine metadata.
        prompt:   Prompt to render and send.
        run_id:   UUID of the owning Run — stamped on OTel metrics and the record.
        attempt:  1-based attempt number (>1 means retry).
        db:       Async SQLAlchemy session — record committed before return.
    """
    rendered = render_prompt(prompt, config.variable_overrides)
    params = PromptParams(
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        timeout_s=config.request_timeout_s,
    )

    start: float = time.perf_counter()
    first_token_time: float | None = None
    chunks: list[str] = []
    meta: ResponseMeta | None = None

    async for chunk in driver.stream_prompt(rendered, str(run_id), params):
        if isinstance(chunk, ResponseMeta):
            meta = chunk  # exact counts from engine
        else:
            if first_token_time is None and chunk.strip():
                first_token_time = time.perf_counter()
            chunks.append(chunk)

    end: float = time.perf_counter()

    total_ms = (end - start) * 1000
    ttft_ms = (first_token_time - start) * 1000 if first_token_time is not None else None

    # Prefer engine-reported counts; fall back to approximations
    prompt_tokens = meta.prompt_tokens if meta else len(rendered.split())
    generated_tokens = meta.generated_tokens if meta else len(chunks)

    # Prefer engine-reported TPS; fall back to wall-clock TPS
    wall_tps = generated_tokens / (end - start) if end > start else None
    tps = (meta.engine_tps if (meta and meta.engine_tps) else wall_tps)

    record = InferenceRecord(
        id=uuid4(),
        run_id=run_id,
        prompt_id=prompt.id,
        attempt=attempt,
        status="success",
        ttft_ms=ttft_ms,
        total_latency_ms=total_ms,
        prompt_tokens=prompt_tokens,
        generated_tokens=generated_tokens,
        tokens_per_second=tps,
        started_at=datetime.now(timezone.utc),
    )

    db.add(record)
    await db.commit()

    # Best-effort ClickHouse write — failure must not abort the benchmark run
    try:
        await ch_insert(
            record,
            model=config.model,
            engine=config.engine,
            host=config.host,
        )
    except Exception as e:  # pragma: no cover — ch_insert already swallows, but be safe
        logger.warning("ch_insert raised unexpectedly run=%s: %s", run_id, e)

    return record
