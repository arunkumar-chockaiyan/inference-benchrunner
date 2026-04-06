# Data Model Diagram

## Entity Relationship Diagram

```mermaid
erDiagram
    PROJECT ||--o{ RUN_CONFIG : has
    PROJECT ||--o{ SAVED_COMPARISON : has

    PROMPT_SUITE ||--o{ SUITE_PROMPT_MAP : contains
    PROMPT ||--o{ SUITE_PROMPT_MAP : "maps to"
    PROMPT_SUITE ||--o{ RUN_CONFIG : uses
    RUN_CONFIG ||--o{ RUN : "creates"

    RUN ||--o{ REQUEST_RECORD : generates
    PROMPT ||--o{ REQUEST_RECORD : "from"

    SAVED_COMPARISON ||--o{ RUN : compares

    ENGINE_MODEL ||--o{ RUN_CONFIG : validates

    PROJECT {
        uuid id PK
        string name UK
        text description
        datetime created_at
    }

    PROMPT {
        uuid id PK
        string name
        text content
        string category
        json variables
        datetime created_at
        datetime updated_at
    }

    PROMPT_SUITE {
        uuid id PK
        string name UK
        text description
        int version
        datetime created_at
        datetime updated_at
    }

    SUITE_PROMPT_MAP {
        uuid suite_id PK, FK
        uuid prompt_id PK, FK
        int position
    }

    RUN_CONFIG {
        uuid id PK
        string name UK
        string engine
        string model
        uuid suite_id FK
        string host
        int port
        int agent_port
        string spawn_mode
        int health_timeout_s
        int concurrency
        float temperature
        int max_tokens
        float top_p
        int request_timeout_s
        int watchdog_interval_s
        int warmup_rounds
        int auto_retry
        json variable_overrides
        text notes
        json tags
        uuid project_id FK
        datetime created_at
    }

    RUN {
        uuid id PK
        uuid config_id FK
        json config_snapshot
        string status
        datetime started_at
        float warmup_duration_ms
        datetime run_started_at
        datetime completed_at
        int total_requests
        int completed_requests
        int failed_requests
        text error_message
        bool server_owned
        int server_pid
        int sidecar_pid
        string remote_agent_run_id
        text cleanup_warning
    }

    REQUEST_RECORD {
        uuid id PK
        uuid run_id FK
        uuid prompt_id FK
        int attempt
        string status
        float ttft_ms
        float total_latency_ms
        int prompt_tokens
        int generated_tokens
        float tokens_per_second
        string error_type
        text error_message
        datetime started_at
    }

    SAVED_COMPARISON {
        uuid id PK
        string name
        text description
        json run_ids
        string metric
        datetime created_at
        string share_token UK
    }

    ENGINE_MODEL {
        uuid id PK
        string engine
        string host
        string model_id
        string display_name
        string source
        datetime last_synced
        bool is_stale
        text notes
        datetime created_at
    }
```

## Key Relationships

### Core Execution Flow
1. **RUN_CONFIG** → **PROMPT_SUITE** (which suite of prompts to run)
2. **RUN_CONFIG** → **RUN** (creates one or more runs)
3. **RUN** → **REQUEST_RECORD** (generates one record per prompt request)
4. **REQUEST_RECORD** ← **PROMPT** (links to the prompt used)

### Prompt Organization
- **PROMPT_SUITE** contains **PROMPT**s via **SUITE_PROMPT_MAP** (preserves order via `position`)
- **SUITE_PROMPT_MAP** is a join table with ordering semantics

### Discovery & Validation
- **ENGINE_MODEL** stores known models per engine+host (populated via sync or manual entry)
- Used to validate **RUN_CONFIG.model** without requiring live engine connection

### Grouping & Analysis
- **PROJECT** groups **RUN_CONFIG**s and **SAVED_COMPARISON**s
- **SAVED_COMPARISON** captures a set of **RUN**s for side-by-side analysis

### Process Tracking
- **RUN** tracks:
  - Timeline: `started_at` → `run_started_at` (sidecar start) → `completed_at`
  - Progress: `total_requests`, `completed_requests`, `failed_requests`
  - Ownership: `server_owned`, `server_pid` (if agent spawned it)
  - Remote: `remote_agent_run_id` (for Tailscale agent coordination)

### Metrics & Results
- **REQUEST_RECORD** captures per-request metrics:
  - `ttft_ms` (time to first token)
  - `total_latency_ms` (total request time)
  - `tokens_per_second` (engine-reported or wall-clock)
  - `prompt_tokens`, `generated_tokens` (from engine ResponseMeta)
  - Retries tracked via `attempt` field

## Constraints & Uniqueness

| Table | Unique Constraint | Notes |
|-------|-------------------|-------|
| PROJECT | name | One name per project |
| PROMPT_SUITE | name | One name per suite |
| RUN_CONFIG | name | One name per config |
| SUITE_PROMPT_MAP | (suite_id, prompt_id) | Composite PK; position enforces order |
| SAVED_COMPARISON | share_token | For shareable URLs |
| ENGINE_MODEL | (engine, host, model_id) | No duplicates per engine+host+model |

## Cascades

- **PROMPT_SUITE** → **SUITE_PROMPT_MAP**: `delete-orphan` (removing suite deletes mappings)
- **PROMPT** → **SUITE_PROMPT_MAP**: `delete-orphan` (removing prompt deletes mappings)
- **RUN** → **REQUEST_RECORD**: `delete-orphan` (deleting run deletes its records)
