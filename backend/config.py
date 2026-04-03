from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://bench:bench@localhost:5432/bench"
    OTEL_COLLECTOR_ENDPOINT: str = "http://otel-collector:4317"
    VICTORIAMETRICS_URL: str = "http://victoriametrics:8428"
    GRAFANA_URL: str = "http://localhost:3001"
    SECRET_KEY: str = "changeme-random-32-bytes"
    AGENT_URL: str = "http://agent:8787"
    AGENT_SECRET_KEY: str = "changeme-agent-secret-key"
    CLICKHOUSE_URL: str = "http://clickhouse:8123"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
