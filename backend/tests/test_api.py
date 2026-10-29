from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_normal_reading():
    result = client.post("/api/predict", json={"temperature": 65, "vibration": 2, "pressure": 7, "current": 48})
    assert result.status_code == 200
    assert result.json()["status"] == "healthy"

def test_bearing_fault():
    result = client.get("/api/machines?scenario=bearing").json()
    machine = result["machines"][1]
    assert machine["anomaly"]
    assert machine["status"] == "critical"
    assert "bearing" in machine["faults"][0]

def test_invalid_reading():
    assert client.post("/api/predict", json={"temperature": 1000, "vibration": 2, "pressure": 7, "current": 48}).status_code == 422

def test_invalid_scenario():
    assert client.get("/api/machines?scenario=unknown").status_code == 422
