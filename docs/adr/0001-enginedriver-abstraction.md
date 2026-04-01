# ADR-0001: EngineDriver Abstraction Pattern

**Date:** 2026-03-31
**Status:** Accepted
**Context:** InferenceBenchRunner must support four different inference engines (Ollama, llama.cpp, vLLM, SGLang) with different APIs and capabilities.

## Problem

Supporting multiple engines naively would lead to:
- Engine-specific code scattered throughout the codebase
- Coupling between `execute_run()` and each engine's API
- Difficulty adding a fifth engine without touching unrelated files
- Testing complexity as each engine is tightly integrated

## Decision

Create an `EngineDriver` abstract base class with a uniform interface:

```python
class EngineDriver(ABC):
    async def spawn(self, model: str, host: str, **kwargs) -> None: ...
    async def wait_healthy(self, timeout_sec: int = 60) -> None: ...
    async def run_prompt(self, prompt: str, **params) -> RequestRecord: ...
    async def teardown(self) -> None: ...
    async def list_models(self, host: str) -> List[str]: ...
```

All engine interactions go through this interface. Each engine gets its own driver file (`ollama_driver.py`, `llamacpp_driver.py`, etc.). A registry maps engine names to driver classes.

## Consequences

**Positive:**
- Adding a new engine requires **zero changes outside its own driver file**
- `execute_run()` is decoupled from engine implementations
- Unit test mocking is trivial (mock the driver interface)
- Easy to test each driver in isolation

**Negative:**
- Requires designing a sufficiently general interface upfront
- Risk of "leaky abstraction" if engines diverge significantly
- Registry maintenance (though lightweight)

## Alternatives Considered

1. **Conditional branching on engine type** — Rejected because coupling spreads across codebase
2. **Factory pattern without ABC** — Rejected because less type-safe and no interface contract
3. **Plugin system with dynamic imports** — Rejected as over-engineered for 4 engines

## Related

- Drivers are instantiated by `execute_run()` at line ~100
- Registry lives in `drivers/__init__.py`
