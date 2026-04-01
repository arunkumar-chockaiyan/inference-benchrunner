# Architecture & Design Review

Scope: overall architecture and design correctness only — not implementation detail.
Source: spec review against `02-engine-drivers.md` prior to Phase 1 build start.

---

## Open Items

### R-01 — Abstract vs. concrete contradiction on `teardown()` and `is_running()`
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The ABC class definition marks `teardown()` and `is_running()` as `@abstractmethod`, but the spec later describes both as concrete methods inherited by all drivers. As written, drivers would be required to implement them, defeating the purpose of the shared concrete implementation.
**Resolution needed:** Remove `@abstractmethod` from both and define them only as concrete methods on the ABC.

---

### R-02 — `list_models(host, port)` signature cannot serve LlamaCppDriver
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The ABC signature is `list_models(self, host: str, port: int)`. LlamaCppDriver's described behaviour is to return `[config.model]`, which requires a `RunConfig`. The interface does not provide one.
**Resolution needed:** Either change the signature to include an optional `config` parameter, or define LlamaCppDriver as always returning `[]` (consistent with "no discovery API") with models registered manually.

---

### R-03 — DB session injection into drivers is undefined
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The `validate_config()` concrete example uses `db.query(...)` directly, but drivers are instantiated via `DRIVERS[engine]()` with no session injection. There is no defined mechanism for drivers to access the DB.
**Resolution needed:** Define how the session is provided — either as a parameter to `validate_config(db, config)`, or as a constructor argument at call time. Must be decided before any driver is implemented.

---

### R-04 — OllamaDriver.validate_config() contradicts the "no live engine call" rule
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The general `validate_config()` principle states it checks the DB registry with no live engine call. Ollama's specific validation additionally runs `shutil.which("ollama")` and `ollama list` (subprocess calls). These are not network calls but they are live system calls, and the exception is not acknowledged in the spec.
**Resolution needed:** Explicitly document that Ollama validate_config() is permitted to make local subprocess calls as an additional safety check on top of the DB registry check, and clarify whether this is the composition pattern (super() + local checks).

---

### R-05 — `config.id` used as `run_id` in `wait_healthy()` — likely wrong identity
**File:** `docs/spec/02-engine-drivers.md`
**Issue:** The managed-mode health URL is built as `/run/{config.id}/health`, treating `RunConfig.id` as the run identifier registered with the agent. If `Run.id` and `RunConfig.id` are different objects (run config is a reusable template; run is a single execution), this is a design bug — the agent would be registered under the wrong ID.
**Resolution needed:** Clarify whether the agent is registered by `Run.id` or `RunConfig.id`, and update `wait_healthy()` to use the correct identifier explicitly. If `run_id` needs to be passed separately, update the method signature.

---

### R-06 — RemoteSpawner (`remote.py`) has no spec
**File:** `docs/spec/02-engine-drivers.md`, build order step 4
**Issue:** `remote.py` appears in both the build order and CLAUDE.md project layout but has no corresponding spec section in `02-engine-drivers.md`. It is unclear what `RemoteSpawner` does, what its interface is, and how it relates to the agent control plane.
**Resolution needed:** Check `05-remote-support.md` for coverage. If not covered there, write the missing spec before step 4 is implemented.

---

### R-07 — `prometheus_client` dependency undeclared
**File:** `docs/spec/02-engine-drivers.md` (ollama_shim), `docs/spec/00-overview.md` stack
**Issue:** `ollama_shim.py` imports `prometheus_client`, but this package does not appear in the declared stack or any requirements file.
**Resolution needed:** Add `prometheus_client` to backend dependencies before the shim is built.

---

## Resolved Items

*(none yet)*
