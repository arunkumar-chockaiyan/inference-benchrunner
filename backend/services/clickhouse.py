"""
ClickHouse write service.

Owns ch_insert() — best-effort columnar write of RequestRecord rows.
A failure here must never raise to the caller; log and return.

Connection uses CLICKHOUSE_URL from config (HTTP interface, port 8123).
"""
from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _do_insert(record, model: str, engine: str, host: str) -> None:
    """Synchronous ClickHouse insert — called via asyncio.to_thread."""
    import clickhouse_connect  # deferred import — optional dependency

    url = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123")
    parsed = urlparse(url)
    ch_host = parsed.hostname or "localhost"
    ch_port = parsed.port or 8123

    client = clickhouse_connect.get_client(host=ch_host, port=ch_port)

    # ClickHouse DateTime64 expects timezone-naive UTC values
    started_at_val = record.started_at
    if hasattr(started_at_val, "tzinfo") and started_at_val.tzinfo is not None:
        started_at_val = started_at_val.replace(tzinfo=None)

    client.insert(
        "inference_requests",
        [[
            str(record.run_id),
            str(record.id),
            model,
            engine,
            host,
            record.prompt_tokens,
            record.generated_tokens,
            record.ttft_ms,
            record.total_latency_ms,
            record.tokens_per_second,
            record.status,
            record.error_type,
            started_at_val,
        ]],
        column_names=[
            "run_id",
            "request_id",
            "model",
            "engine",
            "host",
            "prompt_tokens",
            "gen_tokens",
            "ttft_ms",
            "latency_ms",
            "tokens_per_sec",
            "status",
            "error_type",
            "started_at",
        ],
    )


async def ch_insert(
    record,
    *,
    model: str = "",
    engine: str = "",
    host: str = "",
) -> None:
    """Best-effort write of a RequestRecord to ClickHouse.

    Uses clickhouse-connect (sync client) wrapped in asyncio.to_thread to avoid
    blocking the event loop.

    A failure here MUST NOT raise to the caller — exceptions are logged and
    swallowed so that a ClickHouse outage never aborts a benchmark run.

    Args:
        record:  A RequestRecord ORM instance.
        model:   Model identifier from RunConfig.model.
        engine:  Engine name from RunConfig.engine.
        host:    Engine host from RunConfig.host.
    """
    try:
        await asyncio.to_thread(_do_insert, record, model, engine, host)
    except Exception as e:
        logger.warning("ClickHouse insert failed run=%s: %s", record.run_id, e)
