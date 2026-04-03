# Inference Benchrunner — Data Models

## Dataclasses (not persisted to DB)

### PromptParams

```python
@dataclass
class PromptParams:
    temperature: float = 0.7
    max_tokens:  int   = 512
    top_p:       float = 1.0
    timeout_s:   int   = 120   # per-request timeout — prevents hung requests
```

### ResponseMeta

```python
@dataclass
class ResponseMeta:
    prompt_tokens:    int
    generated_tokens: int
    engine_tps:       float | None  # engine-reported TPS (cross-check vs wall-clock)
                                    # available: Ollama, llama.cpp
                                    # not available: vLLM, SGLang (use wall-clock TPS)
    raw: dict = field(default_factory=dict)  # raw final chunk for debugging
```

### SpawnResult

```python
@dataclass
class SpawnResult:
    owned:       bool        # True = agent spawned it, teardown() must kill it
                             # False = attach mode, teardown() is always no-op
    pid:         int | None  # engine process PID (reported by agent)
    run_id:      str         # run identifier used with agent endpoints
    agent_host:  str         # host where agent runs (localhost or Tailscale addr)
    agent_port:  int         # agent port (default 8787)
```

---

## SQLAlchemy Models

### Prompt

```python
class Prompt(Base):
    id: UUID
    name: str                     # human-readable label
    content: str                  # prompt text, may contain {{variable}} placeholders
    category: str                 # "short"|"long"|"code"|"rag"|"multi_turn"
    variables: dict[str, str]     # JSON column — default values for placeholders
    created_at: datetime
    updated_at: datetime
```

### PromptSuite

```python
class PromptSuite(Base):
    id: UUID
    name: str
    description: str
    version: int                  # auto-incremented on save
    created_at: datetime
    updated_at: datetime

# Association table — preserves prompt order within suite
class SuitePrompt(Base):
    suite_id:  UUID  # FK → PromptSuite.id
    prompt_id: UUID  # FK → Prompt.id
    position:  int   # 0-based order within suite
```

### RunConfig

```python
class RunConfig(Base):
    id: UUID
    name: str                     # e.g. "llama3-vllm-8gpu-2026-03-28"
    engine: str                   # "ollama"|"llamacpp"|"vllm"|"sglang"
    model: str                    # model identifier, engine-specific format
    suite_id: UUID                # FK → PromptSuite.id

    # server location
    host: str                     # "localhost" or Tailscale IP/MagicDNS name
    port: int                     # engine inference port
    agent_port: int               # agent port (default 8787, local and remote)

    # spawn behaviour — two values only
    spawn_mode: str               # "managed" | "attach"
                                  # "managed" = agent spawns + manages engine
                                  #             used for: vLLM, SGLang, llama.cpp
                                  # "attach"  = engine already running, connect directly
                                  #             used for: Ollama (always), pre-running engines
                                  #             teardown is always a no-op in attach mode

    # health check
    health_timeout_s: int         # wait_healthy() timeout (default: 180)
                                  # set 300+ for 70B+ models on slow hardware

    # inference parameters
    concurrency: int              # parallel requests (default: 1)
                                  # max concurrent API calls = concurrency × (auto_retry + 1)
                                  # e.g. concurrency=4, auto_retry=2 → up to 12 simultaneous calls
                                  # tune carefully on weak engines — can cause OOM or cascading timeouts
    temperature: float            # default: 0.7
    max_tokens: int               # default: 512
    top_p: float                  # default: 1.0
    request_timeout_s: int        # per-request timeout seconds (default: 120)

    # run behaviour
    watchdog_interval_s: int          # engine health check interval during run (default: 10)
    warmup_rounds: int            # throwaway requests before recording (default: 3)
    auto_retry: int               # retry failed requests N times (default: 2)
    variable_overrides: dict      # JSON column — override suite prompt variables
    notes: str
    tags: list[str]               # JSON column
    project_id: UUID | None
    created_at: datetime
```

### spawn_mode rules

| spawn_mode  | who spawns engine | teardown       | Ollama? |
|-------------|-------------------|----------------|---------|
| `managed`   | agent             | agent DELETE   | never   |
| `attach`    | nobody (pre-running) | no-op       | always  |

Location (local vs remote) is determined by config.host — not spawn_mode.
The code path is identical for local and remote managed runs.

### Run

```python
class Run(Base):
    id: UUID                          # run_id — stamped on all OTel metrics
    config_id: UUID                   # FK → RunConfig.id
    config_snapshot: dict             # JSON — full RunConfig at start time
                                      # preserves params if config is edited later

    status: str                       # "pending"|"starting"|"warming_up"|"running"
                                      # |"completed"|"failed"|"cancelled"

    # timeline
    started_at: datetime | None       # engine spawned / attached
    warmup_duration_ms: float | None  # total warmup wall time
    run_started_at: datetime | None   # benchmark begins = sidecar start time
                                      # use this to align Grafana charts, not started_at
    completed_at: datetime | None

    # progress
    total_requests: int
    completed_requests: int
    failed_requests: int
    error_message: str | None

    # process tracking
    server_owned: bool                # True = agent spawned it (managed mode)
                                      # False = attach mode, we don't touch it
    server_pid: int | None            # engine PID reported by agent
    sidecar_pid: int | None           # OTel sidecar PID (always local)

    remote_agent_run_id: str | None   # agent's run_id (same as Run.id in practice)
    cleanup_warning: str | None       # set if teardown() could not reach agent
                                      # engine process may still be running
                                      # UI shows warning badge on run card
```

### RequestRecord

```python
class RequestRecord(Base):
    id: UUID
    run_id: UUID                  # FK → Run.id
    prompt_id: UUID               # FK → Prompt.id
    attempt: int                  # 1-based; >1 means retry
    status: str                   # "success"|"error"|"timeout"
    ttft_ms: float | None         # time to first token in milliseconds
    total_latency_ms: float
    prompt_tokens: int            # exact count from engine (ResponseMeta)
    generated_tokens: int         # exact count from engine (ResponseMeta)
    tokens_per_second: float | None  # engine TPS if available, else wall-clock TPS
                                     # NOT directly comparable across engines:
                                     # Ollama/llamacpp = engine-internal timing
                                     # vLLM/SGLang = wall-clock timing
    error_type: str | None
    error_message: str | None
    started_at: datetime
```

### Project

```python
class Project(Base):
    id: UUID
    name: str
    description: str
    created_at: datetime
```

### SavedComparison

```python
class SavedComparison(Base):
    id: UUID
    name: str
    description: str | None       # optional free-text description
    run_ids: list[UUID]           # JSON column
    metric: str                   # "p99"|"ttft"|"throughput"
    created_at: datetime
    share_token: str              # random token for shareable URL
```

### EngineModel

```python
class EngineModel(Base):
    """Known models for a given engine + host combination.
    Populated by sync or manual entry — never requires engine to be running.
    Enables run planning and scheduling without live engine dependency.
    """
    id:           UUID
    engine:       str               # "ollama"|"llamacpp"|"vllm"|"sglang"
    host:         str               # "localhost" or Tailscale IP/MagicDNS name
    model_id:     str               # engine-specific identifier
                                    # Ollama: "llama3:8b"
                                    # llamacpp: "/models/llama-3-8b.gguf" (file path)
                                    # vLLM/SGLang: "meta-llama/Llama-3-8B-Instruct"
    display_name: str               # human-readable label (user-editable)
    source:       str               # "synced" | "manual"
                                    # "synced" = came from list_models() sync
                                    # "manual" = user added directly
                                    # manual records are NEVER overwritten by sync
    last_synced:  datetime | None   # last time seen in a live sync (synced only)
    is_stale:     bool              # True = was synced but absent from most recent
                                    # sync for this engine+host; set by sync endpoint
                                    # always False for source="manual"
    notes:        str               # free-text, e.g. "Q4_K_M quant, needs 8GB VRAM"
    created_at:   datetime

    # composite unique constraint: engine + host + model_id
```

**llamacpp note:** always `source="manual"` — no discovery API exists.
User enters model file path directly. Sync is a no-op for llamacpp.
