import pytest
from fastapi.testclient import TestClient
import os

from agent import app  # Assuming agent/agent.py initializes FastAPI app as `app`

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGENT_SECRET_KEY", "test-secret-key-123")
    return TestClient(app)

def test_spawn_valid_key(client):
    res = client.post("/spawn", headers={"X-Agent-Key": "test-secret-key-123"}, json={
        "engine": "vllm", "model": "meta-llama/Llama-3-8B", "port": 8000,
        "run_id": "abc-123", "extra_args": []
    })
    # Since we can't reliably test actual spawning in a unit test easily without full mocking inside agent,
    # we expect either a 200 (if it mocks/succeeds) or 500 (if binary missing), but NOT 401.
    assert res.status_code != 401

def test_spawn_missing_key(client):
    res = client.post("/spawn", json={
        "engine": "vllm", "model": "test", "port": 8000,
        "run_id": "abc", "extra_args": []
    })
    assert res.status_code == 401
    assert "detail" in res.json()

def test_spawn_wrong_key(client):
    res = client.post("/spawn", headers={"X-Agent-Key": "wrong-key"}, json={
        "engine": "vllm", "model": "test", "port": 8000,
        "run_id": "abc", "extra_args": []
    })
    assert res.status_code == 401

def test_health_exempt_from_auth(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

def test_run_health_auth_required(client):
    res = client.get("/run/abc-123/health")
    assert res.status_code == 401

def test_run_status_auth_required(client):
    res = client.get("/run/abc-123/status")
    assert res.status_code == 401

def test_delete_auth_required(client):
    res = client.delete("/run/abc-123")
    assert res.status_code == 401

def test_missing_agent_secret_key_fails_fast(monkeypatch):
    monkeypatch.delenv("AGENT_SECRET_KEY", raising=False)
    # Reload/Test to see if agent fails or returns 500/401 on missing env var
    client = TestClient(app)
    # The spec dictates it must NOT silently accept any key, so sending an empty/fake key should still be 401
    res = client.get("/run/abc-123/status", headers={"X-Agent-Key": "any-key"})
    assert res.status_code in (401, 500) # Either auth dependency fails 500 or blocks 401
