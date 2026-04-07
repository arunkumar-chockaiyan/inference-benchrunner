import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_engines_list(client):
    res = client.get("/api/engines")
    assert res.status_code == 200
    engine_names = [e["name"] for e in res.json()["engines"]]
    assert "ollama" in engine_names
    assert "llamacpp" in engine_names
    assert "vllm" in engine_names
    assert "sglang" in engine_names

def test_engine_models_crud(client):
    res = client.get("/api/engines/ollama/models")
    assert res.status_code == 200

    # Manual add — no host field
    res_post = client.post("/api/engines/ollama/models", json={
        "model_id": "test_model",
        "display_name": "Test",
        "notes": ""
    })
    assert res_post.status_code in (201, 409)

def test_engine_sync(client):
    # Hits an external engine — expect 200 (synced 0) or 502 (unreachable)
    res = client.post("/api/engines/ollama/models/sync?host=localhost&port=11434")
    assert res.status_code in (200, 502)

def test_llamacpp_sync_is_noop(client):
    # llamacpp has no model listing — returns synced=0 with a message, never 502
    res = client.post("/api/engines/llamacpp/models/sync?host=localhost&port=8080")
    assert res.status_code == 200
    body = res.json()
    assert body["synced"] == 0
    assert "message" in body

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
