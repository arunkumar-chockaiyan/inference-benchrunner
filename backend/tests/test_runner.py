import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

# Assume backend/services/runner.py has `execute_run` and `collect_record`
# Until created, we rely on the tests throwing ImportError to act as TDD requirements

@pytest.mark.asyncio
@patch("services.runner.start_sidecar")
@patch("drivers.get_driver_class")
@patch("services.runner.ClickHouseClient", new_callable=MagicMock)
async def test_execute_run_happy_path(mock_ch_client, mock_get_driver, mock_start_sidecar, db):
    """Scenario 1: Standard benchmark run completing successfully"""
    # Mock driver
    mock_driver_instance = AsyncMock()
    mock_driver_instance.owned = True
    
    # Needs to yield some streaming tokens
    from drivers import ResponseMeta
    async def mock_invoke(*args, **kwargs):
        yield "token1", None
        yield "token2", ResponseMeta(tokens=2)
    mock_driver_instance.invoke_stream = mock_invoke

    mock_get_driver.return_value = MagicMock(return_value=mock_driver_instance)

    # Mock sidecar
    mock_sidecar_proc = AsyncMock()
    mock_start_sidecar.return_value = (mock_sidecar_proc, "/tmp/otel.yaml")

    run_id = uuid.uuid4()
    
    # We would insert a Run, RunConfig, Prompt etc. into `db` here
    # Since the db fixtures are raw, we simulate standard state
    
    from services.runner import execute_run
    
    # Mock fetching the run from DB
    with patch("services.runner.get_run_config_and_prompts") as mock_get_run:
        mock_get_run.return_value = (
            MagicMock(engine="ollama", model="llama", host="localhost", port=11434, variables={}),
            [MagicMock(content="Hey")]
        )
        
        await execute_run(run_id, db)
    
    # Assertions
    mock_driver_instance.spawn.assert_called_once()
    mock_start_sidecar.assert_called_once()
    
    # Assert finally block teardowns
    mock_driver_instance.teardown.assert_called_once()
    mock_sidecar_proc.terminate.assert_called_once()

@pytest.mark.asyncio
async def test_startup_failure_kills_agent():
    # If sidecar fails to start, we must NOT leave the agent running.
    pass

@pytest.mark.asyncio
async def test_clickhouse_best_effort():
    # If clickhouse insert fails, The Run still succeeds (DB records updated)
    pass

@pytest.mark.asyncio
async def test_warmup_excluded_from_metrics():
    # Ensure warmup prompts are sent to engine, but TTFT and records are NOT logged
    pass
