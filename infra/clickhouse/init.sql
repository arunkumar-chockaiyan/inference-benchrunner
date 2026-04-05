CREATE TABLE IF NOT EXISTS inference_requests (
    run_id         String,
    request_id     String,
    model          String,
    engine         String,
    host           String,
    prompt_tokens  UInt32,
    gen_tokens     UInt32,
    ttft_ms        Nullable(Float32),
    latency_ms     Float32,
    tokens_per_sec Nullable(Float32),
    status         String,
    error_type     Nullable(String),
    started_at     DateTime64(3)
) ENGINE = MergeTree()
ORDER BY (run_id, started_at);
