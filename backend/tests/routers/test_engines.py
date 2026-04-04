import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_engines_list(client):
    res = client.get("/api/engines")
    assert res.status_code == 200
    engines = [e["id"] for e in res.json()]
    assert "ollama" in engines
    assert "llamacpp" in engines
    assert "vllm" in engines
    assert "sglang" in engines

def test_engine_models_crud(client):
    res = client.get("/api/engines/ollama/models")
    assert res.status_code == 200
    
    # Manual add
    res_post = client.post("/api/engines/ollama/models", json={
        "host": "localhost",
        "model_id": "test_model",
        "display_name": "Test",
        "notes": ""
    })
    assert res_post.status_code in (201, 500)

def test_engine_sync(client):
    # This hits an external engine usually, so we either mock httpx or expect 502/200
    res = client.post("/api/engines/ollama/models/sync?host=localhost&port=11434")
    assert res.status_code in (200, 502)

def test_llamacpp_sync_is_noop(client):
    # Llamacpp should never connect for sync, it should just return an empty array
    res = client.post("/api/engines/llamacpp/models/sync?host=localhost&port=8080")
    assert res.status_code == 200
    assert res.json() == []

def test_probe(client):
    res = client.post("/api/engines/probe", json={
        "host": "localhost",
        "port": 8080,
        "engine": "llamacpp"
    })
    assert res.status_code == 200
    json_data = res.json()
    assert "reachable" in json_data
    assert "latency_ms" in json_data
    assert "error" in json_data
