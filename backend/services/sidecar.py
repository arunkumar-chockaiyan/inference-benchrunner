"""
OTel sidecar lifecycle service.

Owns start_sidecar() — renders infra/sidecar.yaml.j2 with run context,
spawns otelcol-contrib as an asyncio subprocess, returns
(proc, config_path) for cleanup in execute_run()'s finally block.

See docs/spec/04-otel-sidecar.md for full lifecycle and known limitations.
"""
from __future__ import annotations
# Implementation added in Phase 1 Step 6 (see docs/spec/04-otel-sidecar.md)
