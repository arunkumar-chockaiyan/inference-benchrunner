import pytest
import respx
import httpx
from drivers.llamacpp import LlamaCppDriver

@pytest.mark.asyncio
@respx.mock
async def test_llamacpp_invoke_stream_success():
    driver = LlamaCppDriver(host="localhost", port=8080, model_id="localmodel")
    
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
    async for chunk, meta in driver.invoke_stream("Say Hello"):
        chunks.append(chunk)
        if meta:
            final_meta = meta
            
    assert "".join(chunks) == "Hello World"
    assert final_meta is not None
    assert final_meta.tokens == 2

@pytest.mark.asyncio
@respx.mock
async def test_llamacpp_probe_success():
    driver = LlamaCppDriver(host="localhost", port=8080, model_id="localmodel")
    respx.get("http://localhost:8080/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "localmodel"}]})
    )
    reachable, latency, err = await driver.probe()
    assert reachable is True
    assert err is None
    assert latency > 0
