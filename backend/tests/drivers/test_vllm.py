import pytest
import respx
import httpx
from drivers.vllm import VllmDriver

@pytest.mark.asyncio
@respx.mock
async def test_vllm_invoke_stream_success():
    driver = VllmDriver(host="localhost", port=8000, model_id="neural-chat")
    
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
    async for chunk, meta in driver.invoke_stream("Testing"):
        chunks.append(chunk)
        if meta:
            final_meta = meta
            
    assert "".join(chunks) == "Testing VLLM"
    assert final_meta.tokens == 2
