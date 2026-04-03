"""
Request record collection service.

Owns collect_record() — consumes a stream_prompt() AsyncIterator,
builds a RequestRecord, writes to PostgreSQL, and best-effort writes
to ClickHouse via clickhouse.ch_insert().
"""
from __future__ import annotations
# Implementation added in Phase 1 Step 7 (see docs/spec/03-run-execution.md)
