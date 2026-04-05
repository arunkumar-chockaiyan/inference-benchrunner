import pytest
from unittest.mock import AsyncMock
from drivers import InferenceEngineDriver, ResponseMeta

class DummyDriver(InferenceEngineDriver):
    async def spawn(self, config, run_id):
        from drivers.base import SpawnResult
        return SpawnResult(owned=False, pid=None, run_id=str(run_id), agent_host="localhost", agent_port=8787)

    async def stream_prompt(self, prompt, run_id, params=None):
        yield "a"
        yield ResponseMeta(prompt_tokens=1, generated_tokens=1)

    async def list_models(self, host, port):
        return []

    async def validate_config(self, config, db):
        return []

    def get_metrics_port(self, config):
        return 9091

@pytest.mark.asyncio
async def test_teardown_owned(monkeypatch):
    """Test teardown in managed mode (owned=True)."""
    from drivers.base import SpawnResult
    from unittest.mock import patch

    driver = DummyDriver(host="localhost", port=11434, model_id="dummy")

    # Mock the http client to avoid making real requests
    with patch("drivers.base.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.delete = AsyncMock(return_value=AsyncMock(status_code=200))

        # Create a SpawnResult with owned=True
        result = SpawnResult(
            owned=True,
            pid=1234,
            run_id="test-run-123",
            agent_host="localhost",
            agent_port=8787,
        )

        # Mock the config
        config = AsyncMock()
        config.host = "localhost"
        config.port = 11434

        # Call teardown
        await driver.teardown(config, result)

        # Verify the agent was called to tear down the process
        mock_client.delete.assert_called_once()

@pytest.mark.asyncio
async def test_teardown_attached(monkeypatch):
    """Test teardown in attach mode (owned=False) — should be a no-op."""
    from drivers.base import SpawnResult
    from unittest.mock import patch

    driver = DummyDriver(host="localhost", port=11434, model_id="dummy")

    # Mock the http client
    with patch("drivers.base.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Create a SpawnResult with owned=False (attach mode)
        result = SpawnResult(
            owned=False,
            pid=None,
            run_id="test-run-456",
            agent_host="localhost",
            agent_port=8787,
        )

        # Mock the config
        config = AsyncMock()
        config.host = "localhost"
        config.port = 11434

        # Call teardown
        await driver.teardown(config, result)

        # Verify the agent was NOT called (attach mode = no-op)
        mock_client.delete.assert_not_called()
