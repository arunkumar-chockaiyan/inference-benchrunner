# Inference Benchrunner — Build Order

## Current phase: Phase 1 — not started

Update this file as steps complete. Note any deviations from spec.

---

## Phase 1 — parallelism annotated

Steps with └─> must wait for their parent. Steps at the same indent level
with no arrow can run in parallel.

```
Group A — foundation (sequential):

  [ ] 1. Database models + SQLAlchemy async setup + Alembic init
         Create: backend/database.py, backend/models.py, alembic.ini
         Also: create .env.example with all variables and placeholder values
         Also: create backend/tests/ directory structure

         └─> [ ] 2. InferenceEngineDriver ABC + dataclasses (base.py)
                     Create: backend/drivers/base.py
                     Includes: PromptParams, ResponseMeta, SpawnResult, ABC

                     └─> [ ] 3a. OllamaDriver      (backend/drivers/ollama.py)
                     └─> [ ] 3b. LlamaCppDriver    (backend/drivers/llamacpp.py)  } parallel
                     └─> [ ] 3c. VllmDriver        (backend/drivers/vllm.py)      }
                     └─> [ ] 3d. SGLangDriver      (backend/drivers/sglang.py)    }

                     └─> [ ] 4. RemoteSpawner      (backend/drivers/remote.py)

                     └─> [ ] 5. wait_healthy utility (shared across drivers)


Group B — execution layer (depends on Group A):

  [ ] 6. OTel sidecar template + start_sidecar()
          Create: infra/sidecar.yaml.j2, backend/sidecar.py

          └─> [ ] 7. execute_run() + collect_record() + render_prompt()
                      Create: backend/runner.py

                      └─> [ ] 8. FastAPI routes
                                  - prompts + suites
                                  - engines (list, models, probe)
                                  - runs (CRUD, start, cancel, compare)
                                  Create: backend/main.py, backend/routers/

                                  └─> [ ] 9. WebSocket live progress
                                              Add: /ws/runs/{id} to backend/routers/runs.py


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
- [ ] 22. PostgreSQL migration (Alembic, config change only)

## Phase 3

Do NOT start until triggers hit. See 12-phase3.md.

- [ ] 23. Kafka pipeline
- [ ] 24. ClickHouse consumer + schema
- [ ] 25. Per-request drill-down in compare page
- [ ] 26. Data retention + auto-purge
- [ ] 27. Run scheduler
- [ ] 28. Team member management

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

Run scheduling (Phase 2 step 27) is now supported by the data model:
- EngineModel registry decouples model browsing from engine runtime
- Run.status="pending" already exists — scheduler picks up pending runs
- RunConfig can be created without engine running
- No data model changes needed when scheduler is implemented
