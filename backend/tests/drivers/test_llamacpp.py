import pytest
import respx
import httpx
from unittest.mock import AsyncMock
from drivers.llamacpp import LlamaCppDriver

@pytest.mark.asyncio
@respx.mock
async def test_llamacpp_invoke_stream_success():
    driver = LlamaCppDriver(host="localhost", port=8080, model_id="localmodel")

    # Set up a mock config
    mock_config = AsyncMock()
    mock_config.host = "localhost"
    mock_config.port = 8080
    driver._config = mock_config

    # Mock Llama.cpp SSE OpenAI compatible response
    sse_content = (
        'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": " World"}}], "usage": {"completion_tokens": 2}}\n\n'
        'data: [DONE]\n\n'
    )

    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=sse_content, headers={"Content-Type": "text/event-stream"})
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

