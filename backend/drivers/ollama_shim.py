"""Ollama Prometheus metrics shim.

Standalone script — run as a subprocess by execute_run(), not imported.
Spawned with env vars RUN_ID and MODEL_NAME set by the caller.

Polls http://localhost:11434/api/ps every 5 seconds and exposes two
synthetic Prometheus gauges on port 9091:

  ollama_active_models{run_id}         — number of currently loaded models
  ollama_model_vram_gb{run_id, model}  — VRAM used per model in GB

The OTel sidecar scrapes port 9091, stamping every metric with run_id so
Grafana can filter per-run. The shim is killed in execute_run()'s finally
block after the run completes.

Usage (called by execute_run, not directly):
    python -m drivers.ollama_shim
    # env: RUN_ID=<uuid>, MODEL_NAME=<model-name>
"""
from __future__ import annotations

import os
import time

import httpx
from prometheus_client import Gauge, start_http_server

RUN_ID = os.environ["RUN_ID"]
MODEL_NAME = os.environ["MODEL_NAME"]

_OLLAMA_PS_URL = "http://localhost:11434/api/ps"
_POLL_INTERVAL_S = 5
_METRICS_PORT = 9091

active_models = Gauge(
    "ollama_active_models",
    "Number of models currently loaded in Ollama",
    ["run_id"],
)
model_vram_gb = Gauge(
    "ollama_model_vram_gb",
    "VRAM used by a loaded Ollama model (GB)",
    ["run_id", "model"],
)


def collect() -> None:
    """Poll /api/ps and update gauges. Silently swallows all errors."""
    try:
        r = httpx.get(_OLLAMA_PS_URL, timeout=3).json()
        models = r.get("models", [])
        active_models.labels(run_id=RUN_ID).set(len(models))
        for m in models:
            vram = m.get("size_vram", 0) / 1e9
            model_vram_gb.labels(run_id=RUN_ID, model=m["name"]).set(vram)
    except Exception:
        pass  # Ollama temporarily unreachable — next poll will recover


def main() -> None:
    start_http_server(_METRICS_PORT)
    while True:
        collect()
        time.sleep(_POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
