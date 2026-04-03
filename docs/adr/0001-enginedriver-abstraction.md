# ADR-0001: InferenceEngineDriver Abstraction Pattern

**Date:** 2026-03-31
**Updated:** 2026-04-03
**Status:** Accepted

**Context:** InferenceBenchRunner must support four different inference engines
(Ollama, llama.cpp, vLLM, SGLang) with different APIs, spawn mechanisms, and
metrics endpoints.

## Problem

Supporting multiple engines naively would lead to:
- Engine-specific code scattered throughout the codebase
- Coupling between `execute_run()` and each engine's API
- Difficulty adding a fifth engine without touching unrelated files
- Testing complexity as each engine is tightly integrated

## Decision

Create an `InferenceEngineDriver` abstract base class with a uniform interface,
separating control plane (lifecycle) from data plane (inference):

```python
class InferenceEngineDriver(ABC):
    # --- Control plane (via agent) ---
    @abstractmethod
    async def spawn(self, config: RunConfig, run_id: UUID) -> SpawnResult: ...

    async def wait_healthy(
        self, config: RunConfig, run_id: UUID, timeout: int | None = None
    ) -> None: ...                          # concrete — polls agent health endpoint

    async def teardown(
        self, config: RunConfig, result: SpawnResult
    ) -> None: ...                          # concrete — no-op if result.owned=False

    async def is_healthy(self, config: RunConfig) -> bool: ...  # concrete

    @abstractmethod
    async def validate_config(
        self, config: RunConfig, db: AsyncSession
    ) -> list[str]: ...                     # pre-flight check, no live engine calls

    # --- Data plane (direct to engine, never via agent) ---
    @abstractmethod
    async def stream_prompt(
        self, prompt: str, run_id: str, params: PromptParams | None
    ) -> AsyncIterator[str | ResponseMeta]: ...

    @abstractmethod
    async def list_models(self, host: str, port: int) -> list[str]: ...

    @abstractmethod
    def get_metrics_port(self, config: RunConfig) -> int: ...
```

**Key design rules:**
- `teardown()` and `is_healthy()` are **concrete** methods on the ABC — subclasses inherit the default behaviour and override only if needed
- `spawn_mode` has exactly two values: `"managed"` (agent spawns engine) or `"attach"` (engine pre-running, teardown is no-op)
- Ollama is ALWAYS `"attach"` — it runs as a system service, never managed
- Each engine gets its own driver file: `ollama.py`, `llamacpp.py`, `vllm.py`, `sglang.py`
- A registry maps engine names to driver classes: `DRIVERS` dict in `drivers/__init__.py`

## Consequences

**Positive:**
- Adding a new engine requires **zero changes outside its own driver file**
- `execute_run()` is fully decoupled from engine implementations
- `validate_config()` runs pre-flight checks against the DB registry — no live engine calls needed at planning time
- Control plane / data plane separation prevents token streams from routing through the agent

**Negative:**
- Requires designing a sufficiently general interface upfront
- Risk of "leaky abstraction" if engines diverge significantly
- Registry maintenance (though lightweight)

## Alternatives Considered

1. **Conditional branching on engine type** — Rejected: coupling spreads across codebase
2. **Factory pattern without ABC** — Rejected: less type-safe, no interface contract
3. **Plugin system with dynamic imports** — Rejected: over-engineered for 4 engines

## Related

- ABC + dataclasses: `backend/drivers/base.py`
- Registry: `backend/drivers/__init__.py`
- Instantiation: `backend/runner.py` → `execute_run()`
- Spec: `docs/spec/02-engine-drivers.md`
