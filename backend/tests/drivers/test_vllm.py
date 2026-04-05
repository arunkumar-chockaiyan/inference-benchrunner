import pytest
import respx
import httpx
from unittest.mock import AsyncMock
from drivers.vllm import VllmDriver

@pytest.mark.asyncio
@respx.mock
async def test_vllm_invoke_stream_success():
    driver = VllmDriver(host="localhost", port=8000, model_id="neural-chat")

    # Set up a mock config
    mock_config = AsyncMock()
    mock_config.host = "localhost"
    mock_config.port = 8000
    driver._config = mock_config

    sse_content = (
        'data: {"choices": [{"delta": {"content": "Testing"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": " VLLM"}}], "usage": {"completion_tokens": 2}}\n\n'
        'data: [DONE]\n\n'
    )

    respx.post("http://localhost:8000/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=sse_content, headers={"Content-Type": "text/event-stream"})
    )

    chunks = []
    final_meta = None
    async for item in driver.stream_prompt("Testing", run_id="test-run"):
        if isinstance(item, str):
            chunks.append(item)
        else:
            final_meta = item

    assert "".join(chunks) == "Testing VLLM"
    assert final_meta.generated_tokens == 2
