# Inference Benchrunner — Build Order

## Current phase: Phase 1 — in progress

Update this file as steps complete. Note any deviations from spec.

---

## Phase 1 — parallelism annotated

Steps with └─> must wait for their parent. Steps at the same indent level
with no arrow can run in parallel.

```
Group A — foundation (sequential):

  [x] 1. Database models + SQLAlchemy async setup + Alembic init
         Create: backend/database.py, backend/models.py, alembic.ini
         Also: create .env.example with all variables and placeholder values
         Also: create backend/tests/ directory structure
         Deviation: PostgreSQL (asyncpg) used from Phase 1 — see docs/spec/01-data-models.NOTES.md

         └─> [x] 2. InferenceEngineDriver ABC + dataclasses (base.py)
                     Create: backend/drivers/base.py
                     Includes: PromptParams, ResponseMeta, SpawnResult, ABC

                     └─> [x] 3a. OllamaDriver      (backend/drivers/ollama.py)
                     └─> [x] 3b. LlamaCppDriver    (backend/drivers/llamacpp.py)  } parallel
                     └─> [x] 3c. VllmDriver        (backend/drivers/vllm.py)      }
                     └─> [x] 3d. SGLangDriver      (backend/drivers/sglang.py)    }

                     └─> [N/A] 4. RemoteSpawner (backend/drivers/remote.py)
                                  Removed: remote spawning handled by each driver's spawn()
                                  calling the agent at config.host:config.agent_port directly.
                                  See docs/review.md R-06.

                     └─> [x] 4b. Agent service
                                  Create: agent/agent.py, agent/requirements.txt, agent/Dockerfile
                                  Includes: all 5 endpoints, verify_agent_key dependency,
                                  AGENT_SECRET_KEY validation
                                  Note: agent has no dependency on backend/ code —
                                  can be built in parallel with steps 3a-3d

                     └─> [x] 5. wait_healthy utility (shared across drivers)
                                  Implemented in base.py as concrete method on ABC


Group B — execution layer (depends on Group A):

  [x] 6. OTel sidecar template + start_sidecar()
          Create: infra/sidecar.yaml.j2, backend/services/sidecar.py

          └─> [x] 7. execute_run() + collect_record() + render_prompt() + ch_insert()
                      Create: backend/services/runner.py (execute_run, render_prompt)
                              backend/services/collector.py (collect_record)
                              backend/services/clickhouse.py (ch_insert — best-effort)
                              backend/services/sidecar.py (start_sidecar — moved from sidecar.py)
                      Includes: ClickHouse best-effort write after every PostgreSQL insert

                      └─> [x] 8. FastAPI routes
                                  - prompts + suites
                                  - engines (list, models, probe)
                                  - runs (CRUD, start, cancel, compare)
                                  Created: backend/main.py, backend/routers/
                                  (prompts, suites, engines, runs, comparisons, projects)

                                  └─> [x] 9. WebSocket live progress
                                              Added: /ws/runs/{id} in backend/routers/runs.py (ws_router)


Group C — frontend (can run in parallel with Group B steps 8-9):

  [ ] 10. React frontend
           - run list page
           - new run wizard (4 steps)
           - run detail page
           - compare page
           Create: frontend/src/


Group D — infrastructure (depends on Groups B + C):

  [ ] 11. Docker Compose stack
           Create: docker-compose.yml, infra/otel-collector.yaml
           Includes: postgres, clickhouse, otel-collector, victoriametrics, grafana services
           Also: infra/clickhouse/init.sql (inference_requests schema)

           └─> [ ] 12. Grafana dashboard JSON + provisioning files
                        Create: infra/grafana/provisioning/
```

---

## Phase 2

- [ ] 13. Prompt categories, variable injection, import/export
- [ ] 14. Warmup visibility in UI (warmup_duration_ms display)
- [ ] 15. Parallel run support
- [ ] 16. GPU metrics (nvidia-smi or DCGM exporter)
- [ ] 17. Confidence band computation in compare endpoint
- [ ] 18. Export (CSV, PNG)
- [ ] 19. Saved comparisons + shareable URLs
- [ ] 20. Projects + run notes/tags
- [ ] 21. nginx for frontend (replace Vite dev server)
- [N/A] 22. PostgreSQL migration — skipped: PostgreSQL used from Phase 1

## Phase 3

Do NOT start until triggers hit. See 12-phase3.md.

- [ ] 23. Kafka pipeline — sidecar publishes to Kafka; consumers write to VictoriaMetrics
          and ClickHouse independently. Removes ch_insert() from runner.py (ClickHouse
          writes move to Kafka consumer). Replaces sidecar's otlp exporter with kafka
          exporter. No ClickHouse schema change. See docs/review.md S-10.
- [ ] 24. Per-request drill-down in compare page (timeseries endpoint + LineChart)
- [ ] 25. Data retention + auto-purge
- [ ] 26. Run scheduler
- [ ] 27. Team member management

---

## Parallelism instructions for Claude Code

When given a multi-part task, identify independent subtasks and run them
concurrently using background subagents. Always state what you're running
in parallel before starting. Ask before parallelizing if tasks share files
or have unclear dependencies.

Example — implementing drivers:
  "Implement steps 3a, 3b, 3c, 3d in parallel — one subagent per driver."

---

## Scheduling note

Run scheduling (Phase 3 step 26) is now supported by the data model:
- EngineModel registry decouples model browsing from engine runtime
- Run.status="pending" already exists — scheduler picks up pending runs
- RunConfig can be created without engine running
- No data model changes needed when scheduler is implemented
