import pytest
import respx
import httpx
from drivers.sglang import SglangDriver

@pytest.mark.asyncio
@respx.mock
async def test_sglang_invoke_stream_success():
    # Similar SSE OpenAI implementation expected
    driver = SglangDriver(host="localhost", port=30000, model_id="llama3")
    
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
    async for chunk, meta in driver.invoke_stream("Testing"):
        chunks.append(chunk)
        if meta:
            final_meta = meta
            
    assert "".join(chunks) == "SGLang rocks!"
    assert final_meta.tokens == 3
