import pytest
import respx
import httpx
from drivers.ollama import OllamaDriver

@pytest.mark.asyncio
@respx.mock
async def test_ollama_invoke_stream_success():
    driver = OllamaDriver(host="localhost", port=11434, model_id="llama3")
    
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
    async for chunk, meta in driver.invoke_stream("Say Hello"):
        chunks.append(chunk)
        if meta:
            final_meta = meta
            
    assert "".join(chunks) == "Hello World"
    assert final_meta is not None
    assert final_meta.tokens == 2 # 2 tokens yielded

@pytest.mark.asyncio
@respx.mock
async def test_ollama_invoke_stream_auth_error():
    driver = OllamaDriver(host="localhost", port=11434, model_id="llama3")
    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(401, json={"error": "Unauthorized"})
    )
    
    with pytest.raises(Exception, match="401"):
        async for _ in driver.invoke_stream("Hello"):
            pass
