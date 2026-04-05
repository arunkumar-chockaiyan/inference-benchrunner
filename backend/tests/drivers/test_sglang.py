import pytest
import respx
import httpx
from unittest.mock import AsyncMock
from drivers.sglang import SGLangDriver

@pytest.mark.asyncio
@respx.mock
async def test_sglang_invoke_stream_success():
    # Similar SSE OpenAI implementation expected
    driver = SGLangDriver(host="localhost", port=30000, model_id="llama3")

    # Set up a mock config
    mock_config = AsyncMock()
    mock_config.host = "localhost"
    mock_config.port = 30000
    driver._config = mock_config

    sse_content = (
        'data: {"choices": [{"delta": {"content": "SGLang"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": " rocks!"}}], "usage": {"completion_tokens": 3}}\n\n'
        'data: [DONE]\n\n'
    )

    respx.post("http://localhost:30000/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=sse_content, headers={"Content-Type": "text/event-stream"})
    )

    chunks = []
    final_meta = None
    async for item in driver.stream_prompt("Testing", run_id="test-run"):
        if isinstance(item, str):
            chunks.append(item)
        else:
            final_meta = item

    assert "".join(chunks) == "SGLang rocks!"
    assert final_meta.generated_tokens == 3
