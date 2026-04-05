import pytest
import respx
import httpx
from unittest.mock import AsyncMock
from drivers.ollama import OllamaDriver

@pytest.mark.asyncio
@respx.mock
async def test_ollama_invoke_stream_success():
    driver = OllamaDriver(host="localhost", port=11434, model_id="llama3")

    # Set up a mock config
    mock_config = AsyncMock()
    mock_config.host = "localhost"
    mock_config.port = 11434
    driver._config = mock_config

    # Mock Ollama's NDJSON response
    ndjson_content = (
        '{"model":"llama3","created_at":"2023-08-04T08:52:19.385406455-07:00","response":"Hello","done":false}\n'
        '{"model":"llama3","created_at":"2023-08-04T08:52:19.511781158-07:00","response":" World","done":true, "eval_count": 2}\n'
    )

    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, content=ndjson_content, headers={"Content-Type": "application/x-ndjson"})
    )

    chunks = []
    final_meta = None
    async for item in driver.stream_prompt("Say Hello", run_id="test-run"):
        if isinstance(item, str):
            chunks.append(item)
        else:
            final_meta = item

    assert "".join(chunks) == "Hello World"
    assert final_meta is not None
    assert final_meta.generated_tokens == 2

@pytest.mark.asyncio
@respx.mock
async def test_ollama_invoke_stream_auth_error():
    driver = OllamaDriver(host="localhost", port=11434, model_id="llama3")

    # Set up a mock config
    mock_config = AsyncMock()
    mock_config.host = "localhost"
    mock_config.port = 11434
    driver._config = mock_config

    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(401, json={"error": "Unauthorized"})
    )

    with pytest.raises(Exception, match="401"):
        async for _ in driver.stream_prompt("Hello", run_id="test-run"):
            pass
