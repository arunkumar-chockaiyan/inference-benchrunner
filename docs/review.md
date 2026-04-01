# Architecture & Design Review

Scope: overall architecture and design correctness only — not implementation detail.
Source: spec review against `02-engine-drivers.md` prior to Phase 1 build start.

---

## Open Items

*(none)*

---

## Resolved Items

### R-01 — Abstract vs. concrete contradiction on `teardown()` and `is_running()`
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The ABC class definition marked `teardown()` and `is_running()` as `@abstractmethod`, but the spec later described both as concrete methods inherited by all drivers. As written, drivers would be required to implement them, defeating the purpose of the shared concrete implementation.
**Fix:** Removed `@abstractmethod` from both `teardown()` and `is_running()` in the ABC definition. Both are now concrete methods only, with docstrings updated to note: *"Concrete implementation on ABC — not abstract, all drivers inherit this unchanged."*

---

### R-02 — `list_models(host, port)` signature cannot serve LlamaCppDriver
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The ABC signature is `list_models(self, host: str, port: int)`. LlamaCppDriver's described behaviour is to return `[config.model]`, which requires a `RunConfig`. The interface does not provide one.
**Resolution:** LlamaCppDriver returns `[]` — consistent with "no discovery API". Models are always registered manually. The `[config.model]` description in the original spec was misleading and has been corrected in the sync behaviour table: llamacpp → `returns [] — no discovery API`.

---

### R-03 — DB session injection into drivers is undefined
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The `validate_config()` concrete example used `db.query(...)` directly, but drivers are instantiated via `DRIVERS[engine]()` with no session injection. There was no defined mechanism for drivers to access the DB.
**Fix:** Updated `validate_config()` signature to `validate_config(self, config: RunConfig, db: AsyncSession) -> list[str]` throughout — ABC definition, concrete base example, and all per-driver descriptions. Updated `execute_run()` in `03-run-execution.md` call site to `await driver.validate_config(config, db)`. Session is injected at call time, not at construction.

---

### R-04 — OllamaDriver.validate_config() contradicts the "no live engine call" rule
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The general `validate_config()` principle states it checks the DB registry with no live engine call. Ollama's specific validation additionally runs `shutil.which("ollama")` and `ollama list` (subprocess calls). These are not network calls but they are live system calls, and the exception was not acknowledged in the spec.
**Fix:** Added explicit note to OllamaDriver `validate_config()` description: subprocess calls (`shutil.which`, `ollama list`) are intentional local system checks, not network calls. Documented the composition pattern: call `super().validate_config(config, db)` first for the registry check, then append local system checks.

---

### R-05 — `config.id` used as `run_id` in `wait_healthy()` — likely wrong identity
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The managed-mode health URL was built as `/run/{config.id}/health`, treating `RunConfig.id` as the run identifier registered with the agent. `Run.id` and `RunConfig.id` are different objects — run config is a reusable template; run is a single execution. The agent would be polled under the wrong ID, returning 404.
**Fix:** Updated `spawn()` and `wait_healthy()` ABC signatures to accept `run_id: UUID` as an explicit parameter. Fixed the managed-mode URL in `wait_healthy()` to use `run_id` (Run.id) instead of `config.id`. Updated `execute_run()` call sites in `03-run-execution.md` to `driver.spawn(config, run_id)` and `driver.wait_healthy(config, run_id)`. Added clarifying docstring: *"run_id: Run.id (not RunConfig.id) — registered with agent and used in all subsequent agent calls."*

---

### R-06 — RemoteSpawner (`remote.py`) has no spec
**File:** `docs/spec/02-engine-drivers.md`, build order step 4
**Issue:** `remote.py` appears in both the build order and CLAUDE.md project layout but has no corresponding spec section in `02-engine-drivers.md`. It is unclear what `RemoteSpawner` does, what its interface is, and how it relates to the agent control plane.
**Resolution:** Confirmed covered by `05-remote-support.md`. The universal agent architecture (single FastAPI agent on every host, called via httpx) replaces any need for a separate RemoteSpawner class. `remote.py` as a standalone module is unnecessary — remote spawning is handled by the driver's `spawn()` method posting to the agent at `config.host:config.agent_port`. CLAUDE.md layout entry for `remote.py` is a leftover from an earlier design iteration and should be removed at build time.

---

### R-07 — `prometheus_client` dependency undeclared
**File:** `docs/spec/02-engine-drivers.md` (ollama_shim), `docs/spec/00-overview.md` stack
**Issue:** `ollama_shim.py` imports `prometheus_client`, but this package did not appear in the declared stack or any requirements file.
**Fix:** Added `prometheus-client` to the backend stack in `00-overview.md`: *"Metrics shim: prometheus-client — used by ollama_shim.py to expose synthetic Prometheus /metrics on port 9091."*
