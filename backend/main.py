"""
InferenceBenchRunner — FastAPI backend entrypoint.

Startup:
  - Calls recover_stale_runs() before accepting requests so runs left
    in-progress after a crash are marked failed.

Routers:
  /api/prompts   — prompt CRUD + import/export
  /api/suites    — suite CRUD
  /api/engines   — engine registry, model sync, probe
  /api/runs      — run lifecycle + comparison stats
  /api/comparisons — saved comparisons
  /api/projects  — project grouping

WebSocket:
  /ws/runs/{id}  — live run progress stream (registered via ws_router)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.runner import recover_stale_runs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="InferenceBenchRunner",
    version="1.0.0",
    description="LLM inference engine benchmarking API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    """Recover any runs left in-progress from a previous backend crash."""
    await recover_stale_runs()


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from routers.prompts import router as prompts_router          # noqa: E402
from routers.suites import router as suites_router            # noqa: E402
from routers.engines import router as engines_router          # noqa: E402
from routers.runs import router as runs_router                # noqa: E402
from routers.runs import ws_router                            # noqa: E402
from routers.comparisons import router as comparisons_router  # noqa: E402
from routers.projects import router as projects_router        # noqa: E402

app.include_router(prompts_router)
app.include_router(suites_router)
app.include_router(engines_router)
app.include_router(runs_router)
app.include_router(ws_router)          # WebSocket routes — no /api prefix
app.include_router(comparisons_router)
app.include_router(projects_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
