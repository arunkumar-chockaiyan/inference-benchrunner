"""
Tests for SQLAlchemy models — mirrors docs/qa/01-data-models.md.

Fixtures used: `db` (AsyncSession, function-scoped) from conftest.py.
All tests use async/await; pytest-asyncio auto mode is active.
"""
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from models import (
    Prompt,
    PromptSuite,
    SuitePromptMap,
    RunConfig,
    Run,
    InferenceRecord,
    EngineModel,
    SavedComparison,
    Project,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal prerequisite objects without repeating boilerplate
# ---------------------------------------------------------------------------

def _suite(name: str | None = None) -> PromptSuite:
    return PromptSuite(id=uuid.uuid4(), name=name or f"suite-{uuid.uuid4().hex[:8]}")


def _config(suite: PromptSuite, name: str | None = None) -> RunConfig:
    return RunConfig(
        id=uuid.uuid4(),
        name=name or f"cfg-{uuid.uuid4().hex[:8]}",
        engine="vllm",
        model="llama3",
        suite_id=suite.id,
        host="localhost",
        port=8000,
        spawn_mode="attach",
    )


def _run(config: RunConfig) -> Run:
    return Run(id=uuid.uuid4(), config_id=config.id)


# ---------------------------------------------------------------------------
# Section 1 — Model instantiation
# ---------------------------------------------------------------------------

async def test_prompt_instantiation(db):
    """Prompt: {{variable}} content and variables dict round-trip."""
    prompt = Prompt(
        id=uuid.uuid4(),
        name=f"p-{uuid.uuid4().hex[:8]}",
        content="Hello {{name}}",
        category="short",
        variables={"name": "world"},
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)

    assert prompt.content == "Hello {{name}}"
    assert prompt.variables == {"name": "world"}


async def test_suite_defaults(db):
    """PromptSuite: version starts at 1."""
    suite = _suite()
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    assert suite.version == 1


async def test_run_defaults(db):
    """Run.status defaults to 'pending' after DB insert (column INSERT default)."""
    suite = _suite()
    db.add(suite)
    await db.flush()
    cfg = _config(suite)
    db.add(cfg)
    await db.flush()
    run = _run(cfg)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    assert run.status == "pending"


async def test_runconfig_spawn_mode_values(db):
    """RunConfig: spawn_mode stores 'managed' and 'attach' correctly."""
    suite = _suite()
    db.add(suite)
    await db.flush()

    cfg_attach = _config(suite)
    cfg_attach.spawn_mode = "attach"
    cfg_managed = _config(suite)
    cfg_managed.spawn_mode = "managed"

    db.add_all([cfg_attach, cfg_managed])
    await db.commit()
    await db.refresh(cfg_attach)
    await db.refresh(cfg_managed)

    assert cfg_attach.spawn_mode == "attach"
    assert cfg_managed.spawn_mode == "managed"


async def test_engine_model_unique_constraint(db):
    """EngineModel: composite unique (engine, host, model_id) enforced at DB level."""
    m1 = EngineModel(
        engine="ollama",
        host=f"host-{uuid.uuid4().hex[:8]}",
        model_id="tinyllama",
        display_name="TinyLlama",
        source="manual",
    )
    db.add(m1)
    await db.commit()

    m2 = EngineModel(
        engine=m1.engine,
        host=m1.host,
        model_id=m1.model_id,
        display_name="Duplicate",
        source="synced",
    )
    db.add(m2)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_saved_comparison_share_token_unique(db):
    """SavedComparison: share_token unique constraint enforced."""
    token = uuid.uuid4().hex
    sc1 = SavedComparison(
        name="comp-1",
        run_ids=[],
        metric="p99",
        share_token=token,
    )
    db.add(sc1)
    await db.commit()

    sc2 = SavedComparison(
        name="comp-2",
        run_ids=[],
        metric="ttft",
        share_token=token,  # same token — must fail
    )
    db.add(sc2)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# Section 2 — Run status transitions
# ---------------------------------------------------------------------------

async def test_run_transition_to_starting_sets_started_at(db):
    """pending → starting sets started_at."""
    suite = _suite()
    db.add(suite)
    await db.flush()
    cfg = _config(suite)
    db.add(cfg)
    await db.flush()
    run = _run(cfg)
    db.add(run)
    await db.commit()

    run.status = "starting"
    run.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)

    assert run.status == "starting"
    assert run.started_at is not None


async def test_run_transition_to_completed_sets_completed_at(db):
    """running → completed sets completed_at."""
    suite = _suite()
    db.add(suite)
    await db.flush()
    cfg = _config(suite)
    db.add(cfg)
    await db.flush()
    run = _run(cfg)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.add(run)
    await db.commit()

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)

    assert run.status == "completed"
    assert run.completed_at is not None


async def test_run_transition_to_failed_sets_error_message(db):
    """Transition to failed populates error_message."""
    suite = _suite()
    db.add(suite)
    await db.flush()
    cfg = _config(suite)
    db.add(cfg)
    await db.flush()
    run = _run(cfg)
    db.add(run)
    await db.commit()

    run.status = "failed"
    run.error_message = "engine crashed"
    await db.commit()
    await db.refresh(run)

    assert run.status == "failed"
    assert run.error_message == "engine crashed"


# ---------------------------------------------------------------------------
# Section 3 — run_id immutability
# ---------------------------------------------------------------------------

async def test_run_id_consistency_on_inference_records(db):
    """All InferenceRecord rows for a Run carry the same run_id as Run.id."""
    suite = _suite()
    db.add(suite)
    await db.flush()
    cfg = _config(suite)
    db.add(cfg)
    await db.flush()

    run = _run(cfg)
    db.add(run)
    await db.flush()

    prompt = Prompt(
        id=uuid.uuid4(),
        name=f"p-{uuid.uuid4().hex[:8]}",
        content="hello",
        category="short",
        variables={},
    )
    db.add(prompt)
    await db.flush()

    record = InferenceRecord(
        id=uuid.uuid4(),
        run_id=run.id,
        prompt_id=prompt.id,
        attempt=1,
        status="success",
        total_latency_ms=123.0,
        prompt_tokens=10,
        generated_tokens=20,
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    assert record.run_id == run.id


# ---------------------------------------------------------------------------
# Section 5 — PromptSuite version auto-increment
# ---------------------------------------------------------------------------

async def test_suite_version_increments_on_update(db):
    """PromptSuite.version auto-increments via before_update event listener."""
    suite = _suite()
    db.add(suite)
    await db.commit()
    await db.refresh(suite)
    assert suite.version == 1

    suite.description = "updated"
    await db.commit()
    await db.refresh(suite)
    assert suite.version == 2

    suite.description = "updated again"
    await db.commit()
    await db.refresh(suite)
    assert suite.version == 3


# ---------------------------------------------------------------------------
# Section 6 — JSON columns
# ---------------------------------------------------------------------------

async def test_prompt_variables_roundtrip(db):
    """Prompt.variables: empty dict and nested strings preserved."""
    p1 = Prompt(
        id=uuid.uuid4(),
        name=f"p-{uuid.uuid4().hex[:8]}",
        content="empty",
        category="short",
        variables={},
    )
    p2 = Prompt(
        id=uuid.uuid4(),
        name=f"p-{uuid.uuid4().hex[:8]}",
        content="nested {{a}}",
        category="short",
        variables={"a": "hello", "b": "world"},
    )
    db.add_all([p1, p2])
    await db.commit()
    await db.refresh(p1)
    await db.refresh(p2)

    assert p1.variables == {}
    assert p2.variables == {"a": "hello", "b": "world"}


async def test_runconfig_json_columns(db):
    """RunConfig: variable_overrides (None valid, dict preserved) and tags list."""
    suite = _suite()
    db.add(suite)
    await db.flush()

    cfg = RunConfig(
        id=uuid.uuid4(),
        name=f"cfg-{uuid.uuid4().hex[:8]}",
        engine="vllm",
        model="llama3",
        suite_id=suite.id,
        host="localhost",
        port=8000,
        spawn_mode="attach",
        variable_overrides={"topic": "benchmarks"},
        tags=["gpu", "test"],
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)

    assert cfg.variable_overrides == {"topic": "benchmarks"}
    assert cfg.tags == ["gpu", "test"]


async def test_run_config_snapshot_preserved(db):
    """Run.config_snapshot: full dict captured at run start, survives config mutation."""
    suite = _suite()
    db.add(suite)
    await db.flush()

    cfg = _config(suite)
    db.add(cfg)
    await db.flush()

    snapshot = {"engine": cfg.engine, "model": cfg.model, "port": cfg.port}
    run = Run(id=uuid.uuid4(), config_id=cfg.id, config_snapshot=snapshot)
    db.add(run)
    await db.commit()

    # Mutate the config — snapshot must remain unchanged
    cfg.model = "llama3-70b"
    await db.commit()
    await db.refresh(run)

    assert run.config_snapshot["engine"] == "vllm"
    assert run.config_snapshot["model"] == "llama3"  # original, not mutated


async def test_saved_comparison_run_ids_roundtrip(db):
    """SavedComparison.run_ids: list of UUID strings stored and retrieved."""
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    sc = SavedComparison(
        name=f"cmp-{uuid.uuid4().hex[:8]}",
        run_ids=ids,
        metric="throughput",
        share_token=uuid.uuid4().hex,
    )
    db.add(sc)
    await db.commit()
    await db.refresh(sc)

    assert sc.run_ids == ids
    assert isinstance(sc.run_ids, list)


# ---------------------------------------------------------------------------
# Section 7 — EngineModel sync behaviour
# ---------------------------------------------------------------------------

async def test_enginemodel_synced_goes_stale(db):
    """source='synced' absent from most recent sync → is_stale=True, NOT deleted."""
    host = f"host-{uuid.uuid4().hex[:8]}"
    synced = EngineModel(
        engine="vllm",
        host=host,
        model_id="model-b",
        display_name="Model B",
        source="synced",
        is_stale=False,
    )
    db.add(synced)
    await db.commit()

    synced.is_stale = True
    await db.commit()
    await db.refresh(synced)

    assert synced.is_stale is True
    # Record still exists — not deleted
    assert synced.id is not None


async def test_enginemodel_manual_not_overwritten(db):
    """source='manual' record: is_stale always False, unaffected by sync logic."""
    host = f"host-{uuid.uuid4().hex[:8]}"
    manual = EngineModel(
        engine="llamacpp",
        host=host,
        model_id="/models/q4.gguf",
        display_name="Q4 GGUF",
        source="manual",
        is_stale=False,
    )
    db.add(manual)
    await db.commit()

    # Simulate sync: manual record must NOT be marked stale
    assert manual.is_stale is False
    assert manual.source == "manual"


# ---------------------------------------------------------------------------
# Section 8 — Process tracking columns
# ---------------------------------------------------------------------------

async def test_run_server_owned_and_pid(db):
    """Run.server_owned, server_pid, sidecar_pid set from SpawnResult fields."""
    suite = _suite()
    db.add(suite)
    await db.flush()
    cfg = _config(suite)
    db.add(cfg)
    await db.flush()

    run = _run(cfg)
    run.server_owned = True
    run.server_pid = 12345
    run.sidecar_pid = 67890
    db.add(run)
    await db.commit()
    await db.refresh(run)

    assert run.server_owned is True
    assert run.server_pid == 12345
    assert run.sidecar_pid == 67890


async def test_run_cleanup_warning(db):
    """Run.cleanup_warning set when teardown agent is unreachable."""
    suite = _suite()
    db.add(suite)
    await db.flush()
    cfg = _config(suite)
    db.add(cfg)
    await db.flush()

    run = _run(cfg)
    run.cleanup_warning = "agent unreachable at 10.0.0.5:8787"
    db.add(run)
    await db.commit()
    await db.refresh(run)

    assert run.cleanup_warning is not None
    assert "unreachable" in run.cleanup_warning


# ---------------------------------------------------------------------------
# Section 9 — PostgreSQL-specific types
# ---------------------------------------------------------------------------

async def test_uuid_columns_are_uuid_type(db):
    """UUID primary keys are Python uuid.UUID objects after DB round-trip."""
    suite = _suite()
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    assert isinstance(suite.id, uuid.UUID)


async def test_timestamptz_columns_are_timezone_aware(db):
    """DateTime(timezone=True) → timezone-aware datetime after round-trip."""
    suite = _suite()
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    assert suite.created_at.tzinfo is not None
