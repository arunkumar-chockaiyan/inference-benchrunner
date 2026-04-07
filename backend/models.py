import uuid
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    UUID,
    JSON,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # short|long|code|rag|multi_turn
    variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    suite_entries: Mapped[list["SuitePromptMap"]] = relationship("SuitePromptMap", back_populates="prompt", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# PromptSuite + association
# ---------------------------------------------------------------------------

class PromptSuite(Base):
    __tablename__ = "prompt_suites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    prompts: Mapped[list["SuitePromptMap"]] = relationship("SuitePromptMap", back_populates="suite", order_by="SuitePromptMap.position", cascade="all, delete-orphan")
    run_configs: Mapped[list["RunConfig"]] = relationship("RunConfig", back_populates="suite")


@event.listens_for(PromptSuite, "before_update")
def _increment_suite_version(mapper, connection, target: "PromptSuite") -> None:
    """Auto-increment version on every update — tracks suite revisions."""
    target.version = (target.version or 0) + 1


class SuitePromptMap(Base):
    __tablename__ = "suite_prompt_map"

    suite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("prompt_suites.id"), primary_key=True)
    prompt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("prompts.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    suite: Mapped["PromptSuite"] = relationship("PromptSuite", back_populates="prompts")
    prompt: Mapped["Prompt"] = relationship("Prompt", back_populates="suite_entries")


# ---------------------------------------------------------------------------
# RunConfig
# ---------------------------------------------------------------------------

class RunConfig(Base):
    __tablename__ = "run_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    engine: Mapped[str] = mapped_column(String, nullable=False)   # ollama|llamacpp|vllm|sglang
    model: Mapped[str] = mapped_column(String, nullable=False)
    suite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("prompt_suites.id"), nullable=False)

    # server location
    host: Mapped[str] = mapped_column(String, nullable=False, default="localhost")
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8787)

    # spawn behaviour
    spawn_mode: Mapped[str] = mapped_column(String, nullable=False, default="attach")  # managed|attach

    # health check
    health_timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=180)

    # inference parameters
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=512)
    top_p: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    request_timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=120)

    # run behaviour
    watchdog_interval_s: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    warmup_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    auto_retry: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    variable_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    suite: Mapped["PromptSuite"] = relationship("PromptSuite", back_populates="run_configs")
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="config")
    project: Mapped["Project | None"] = relationship("Project", back_populates="run_configs")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("run_configs.id"), nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # pending|starting|warming_up|running|completed|failed|cancelled

    # timeline
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warmup_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # progress
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # process tracking
    server_owned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    server_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sidecar_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)

    remote_agent_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cleanup_warning: Mapped[str | None] = mapped_column(Text, nullable=True)

    config: Mapped["RunConfig"] = relationship("RunConfig", back_populates="runs")
    records: Mapped[list["InferenceRecord"]] = relationship("InferenceRecord", back_populates="run", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# InferenceRecord
# ---------------------------------------------------------------------------

class InferenceRecord(Base):
    __tablename__ = "inference_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    prompt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("prompts.id"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False)  # success|error|timeout
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped["Run"] = relationship("Run", back_populates="records")
    prompt: Mapped["Prompt"] = relationship("Prompt")


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    run_configs: Mapped[list["RunConfig"]] = relationship("RunConfig", back_populates="project")


# ---------------------------------------------------------------------------
# SavedComparison
# ---------------------------------------------------------------------------

class SavedComparison(Base):
    __tablename__ = "saved_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metric: Mapped[str] = mapped_column(String, nullable=False)  # p99|ttft|throughput
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    share_token: Mapped[str] = mapped_column(String, nullable=False, unique=True)


# ---------------------------------------------------------------------------
# EngineModel
# ---------------------------------------------------------------------------

class EngineModel(Base):
    __tablename__ = "engine_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engine: Mapped[str] = mapped_column(String, nullable=False)       # ollama|llamacpp|vllm|sglang
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)        # synced|manual
    last_synced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True = was synced but absent from most recent sync for this engine
    # Always False for source="manual" — never overwritten by sync
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("engine", "model_id", name="uq_engine_model"),
    )
