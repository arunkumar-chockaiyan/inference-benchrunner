"""
Run orchestration service.

Owns execute_run() — spawns the engine, runs warmup, fires prompts,
collects records, tears down the engine.

Delegates to:
  - collector.run_one()     for per-request record collection
  - sidecar.start_sidecar() for OTel sidecar lifecycle
  - drivers registry        for engine control/data plane
"""
from __future__ import annotations
# Implementation added in Phase 1 Step 7 (see docs/spec/03-run-execution.md)
