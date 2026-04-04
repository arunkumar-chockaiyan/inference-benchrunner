import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from models import (
    Prompt,
    PromptSuite,
    SuitePrompt,
    RunConfig,
    Run,
    RequestRecord,
    EngineModel,
    SavedComparison,
)

@pytest.mark.asyncio
async def test_prompt_instantiation(db):
    prompt = Prompt(
        id=uuid.uuid4(),
        name="test-prompt",
        content="Hello {{name}}",
        category="test",
        variables={"name": "world"}
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    
    assert prompt.content == "Hello {{name}}"
    assert prompt.variables == {"name": "world"}

@pytest.mark.asyncio
async def test_suite_version_increment(db):
    suite = PromptSuite(id=uuid.uuid4(), name="test-suite")
    db.add(suite)
    await db.commit()
    await db.refresh(suite)
    assert suite.version == 1

    suite.name = "renamed-suite"
    await db.commit()
    await db.refresh(suite)
    assert suite.version == 2

@pytest.mark.asyncio
async def test_run_status_transitions(db):
    run_id = uuid.uuid4()
    run = Run(id=run_id)
    assert run.status == "pending"

    # Pending -> Starting
    run.status = "starting"
    run.started_at = datetime.now(timezone.utc)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    assert run.status == "starting"
    assert run.started_at is not None

    # Starting -> Completed
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    assert run.status == "completed"
    assert run.completed_at is not None

@pytest.mark.asyncio
async def test_enginemodel_unique_constraint(db):
    model1 = EngineModel(
        engine="ollama",
        host="localhost",
        model_id="tinyllama",
        display_name="TinyLlama",
        source="manual"
    )
    db.add(model1)
    await db.commit()

    model2 = EngineModel(
        engine="ollama",
        host="localhost",
        model_id="tinyllama",
        display_name="Duplicate",
        source="synced"
    )
    db.add(model2)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()

@pytest.mark.asyncio
async def test_run_id_immutability(db):
    run_id = uuid.uuid4()
    run = Run(id=run_id)
    db.add(run)
    await db.commit()
    
    # SQLAlchemy does not easily allow updating Primary Keys anyway, but we test the attempt
    run.id = uuid.uuid4()
    db.add(run)
    with pytest.raises(Exception): # Will depend on dialect behavior (usually IntegrityError)
        await db.flush()
    await db.rollback()

@pytest.mark.asyncio
async def test_json_columns(db):
    run_id = uuid.uuid4()
    config = RunConfig(
        id=uuid.uuid4(),
        engine="vllm",
        model="llama3",
        host="localhost",
        port=8000,
        spawn_mode="attach",
        variable_overrides={"foo": "bar"},
        tags=["gpu", "test"]
    )
    run = Run(id=run_id, config_id=config.id, config_snapshot=config.model_dump())
    db.add_all([config, run])
    await db.commit()
    await db.refresh(config)
    await db.refresh(run)
    
    assert config.variable_overrides == {"foo": "bar"}
    assert config.tags == ["gpu", "test"]
    assert run.config_snapshot["engine"] == "vllm"

@pytest.mark.asyncio
async def test_engine_model_sync_behavior(db):
    # manual model
    manual = EngineModel(engine="sglang", host="localhost", model_id="a", source="manual")
    # synced model
    synced = EngineModel(engine="sglang", host="localhost", model_id="b", source="synced", is_stale=False)
    db.add_all([manual, synced])
    await db.commit()

    # simulate sync not returning "b"
    synced.is_stale = True
    await db.commit()
    await db.refresh(synced)
    assert synced.is_stale is True
