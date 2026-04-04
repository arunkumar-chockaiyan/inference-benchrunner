import pytest
from fastapi.testclient import TestClient
import uuid
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_create_run_missing_fields(client):
    res = client.post("/api/runs", json={"engine": "ollama"})
    assert res.status_code == 422
    assert "detail" in res.json()

def test_get_run_not_found(client):
    res = client.get(f"/api/runs/{uuid.uuid4()}")
    assert res.status_code == 404
    assert "detail" in res.json()

def test_compare_routing_precedence(client):
    """
    Test that /api/runs/compare handles as 'compare', not trying to parse 'compare' as a UUID
    resulting in a 422 for GET /api/runs/{id}
    """
    res = client.post("/api/runs/compare", json={"run_ids": [str(uuid.uuid4())], "metric": "p99"})
    assert res.status_code == 200

def test_compare_invalid_metric(client):
    res = client.post("/api/runs/compare", json={"run_ids": [str(uuid.uuid4())], "metric": "invalid_metric"})
    assert res.status_code == 422

def test_run_list_filters(client):
    res = client.get("/api/runs?status=completed&engine=vllm&tag=gpu-test")
    assert res.status_code == 200

def test_delete_run_not_found(client):
    res = client.delete(f"/api/runs/{uuid.uuid4()}")
    assert res.status_code == 404

def test_error_shape(client):
    res = client.get(f"/api/runs/{uuid.uuid4()}")
    assert res.status_code == 404
    assert "detail" in res.json()
    assert isinstance(res.json()["detail"], str)

def test_websocket_stream_unknown_id(client):
    # Test websocket connection failure on unknown id
    with pytest.raises(Exception) as exc:
        with client.websocket_connect("/ws/runs/nonexistent-id") as websocket:
            websocket.receive_json()
    # It should close immediately with 1008
    assert "1008" in str(exc.value) or "1008" in str(exc.type) or "close" in str(exc.value).lower()
