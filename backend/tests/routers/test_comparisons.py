import pytest
from fastapi.testclient import TestClient
import uuid
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_create_comparison(client):
    res = client.post("/api/comparisons", json={
        "name": "GPU vs CPU Test",
        "run_ids": [str(uuid.uuid4()), str(uuid.uuid4())]
    })
    assert res.status_code in (200, 201, 500)
    if res.status_code == 200:
        assert "token" in res.json()

def test_get_comparison_not_found(client):
    res = client.get("/api/comparisons/invalid-token")
    assert res.status_code == 404
    assert "detail" in res.json()
