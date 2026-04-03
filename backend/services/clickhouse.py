"""
ClickHouse write service.

Owns ch_insert() — best-effort columnar write of RequestRecord rows.
A failure here must never raise to the caller; log and return.

Connection uses CLICKHOUSE_URL from config (HTTP interface, port 8123).
"""
from __future__ import annotations
# Implementation added in Phase 1 Step 7 (see docs/spec/01-data-models.md § ClickHouse)
