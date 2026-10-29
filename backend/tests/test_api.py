import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.main as main

client = TestClient(app)

@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test.db"))


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


def test_history_records_actual_snapshots():
    first = client.get("/api/machines?scenario=overheating").json()
    second = client.get("/api/machines?scenario=normal").json()
    history = client.get("/api/machines/M-001/history").json()["readings"]
    assert len(history) == 2
    assert history[0]["temperature"] == first["machines"][0]["sensors"]["temperature"]
    assert history[1]["temperature"] == second["machines"][0]["sensors"]["temperature"]
    assert second["machines"][0]["temperature_history"] == [row["temperature"] for row in history]


def test_work_order_lifecycle():
    created = client.post("/api/work-orders", json={"machine_id": "M-002", "title": "Inspect bearing"})
    assert created.status_code == 201
    order = created.json()
    assert order["status"] == "open"
    assert client.get("/api/work-orders").json()["work_orders"][0]["id"] == order["id"]
    assert client.patch(f"/api/work-orders/{order['id']}", json={"status": "completed"}).json()["status"] == "completed"
    assert client.patch(f"/api/work-orders/{order['id']}", json={"status": "invalid"}).status_code == 422


def test_unknown_resources_and_empty_titles():
    assert client.get("/api/machines/unknown/history").status_code == 404
    assert client.post("/api/work-orders", json={"machine_id": "unknown", "title": "Inspect"}).status_code == 404
    assert client.post("/api/work-orders", json={"machine_id": "M-001", "title": "   "}).status_code == 422
    assert client.patch("/api/work-orders/missing", json={"status": "completed"}).status_code == 404


@pytest.fixture
def simulator_contract(monkeypatch):
    import json
    from pathlib import Path
    import httpx
    import app.simulator as simulator
    fixtures = Path(__file__).parent / "fixtures"
    catalog = json.loads((fixtures / "catalog.json").read_text())
    telemetry = json.loads((fixtures / "telemetry.json").read_text())
    original_client = httpx.Client
    def respond(request):
        if request.url.path == "/machines":
            return httpx.Response(200, json=catalog)
        assert request.url.path == "/fleet/telemetry"
        assert request.url.params["count"] == "1"
        return httpx.Response(200, json=telemetry)
    monkeypatch.setenv("SIAS_SIMULATOR_URL", "https://simulator.example")
    monkeypatch.setattr(simulator.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    return catalog, telemetry


def test_sias_baselines_and_units(simulator_contract):
    result = client.get("/api/machines?source=sias").json()
    assert result["data_source"] == "sias"
    extruder = result["machines"][0]
    assert extruder["id"] == "extruder-01"
    assert extruder["status"] == "healthy"  # 184 C and 122 bar are normal for this asset.
    assert extruder["sensors"]["current"] is None
    assert extruder["sensors"]["power"] == 62
    assert extruder["risk"] == 0
    history = client.get("/api/machines/extruder-01/history").json()["readings"]
    assert history[0]["current"] is None
    assert history[0]["power"] == 62
    assert client.post("/api/work-orders", json={"machine_id":"extruder-01", "title":"Inspect motor"}).status_code == 201


def test_sias_fault_relative_to_baseline(simulator_contract):
    _, telemetry = simulator_contract
    telemetry["samples"][0]["readings"][0]["temperature_c"] = 270
    response = client.get("/api/machines?source=sias&scenario=overheating")
    assert response.status_code == 200
    machine = response.json()["machines"][0]
    assert machine["status"] == "critical"
    assert machine["anomaly"] is True
    assert "Possible overheating" in machine["faults"]


def test_unconfigured_sias_is_explicit(monkeypatch):
    monkeypatch.delenv("SIAS_SIMULATOR_URL", raising=False)
    response = client.get("/api/machines?source=sias")
    assert response.status_code == 503
    assert "SIAS simulator unavailable" in response.json()["detail"]


def test_invalid_sias_contract_not_silently_replaced(simulator_contract):
    _, telemetry = simulator_contract
    telemetry["samples"][0]["readings"] = []
    assert client.get("/api/machines?source=sias").status_code == 503


def test_old_database_migrates_without_losing_readings(tmp_path):
    import sqlite3
    with sqlite3.connect(main.DB_PATH) as connection:
        connection.execute("CREATE TABLE readings (id INTEGER PRIMARY KEY, machine_id TEXT, timestamp TEXT, temperature REAL, vibration REAL, pressure REAL, current REAL, risk REAL, status TEXT)")
        connection.execute("INSERT INTO readings VALUES (1, 'M-001', '2026-10-29T00:00:00+00:00', 65, 2, 7, 48, 0, 'healthy')")
    response = client.get("/api/machines/M-001/history")
    assert response.status_code == 200
    assert response.json()["readings"][0]["current"] == 48
    assert response.json()["readings"][0]["power"] is None


def test_work_orders_survive_process_restart(tmp_path):
    import json
    import os
    import subprocess
    import sys
    env = {**os.environ, "DATABASE_PATH": str(tmp_path / "restart.db")}
    create = subprocess.run([sys.executable, "-c", "from fastapi.testclient import TestClient; from app.main import app; import json; print(json.dumps(TestClient(app).post('/api/work-orders', json={'machine_id':'M-001','title':'Restart persistence check'}).json()))"], env=env, capture_output=True, text=True, check=True, timeout=60)
    created = json.loads(create.stdout)
    read = subprocess.run([sys.executable, "-c", "from fastapi.testclient import TestClient; from app.main import app; import json; print(json.dumps(TestClient(app).get('/api/work-orders').json()))"], env=env, capture_output=True, text=True, check=True, timeout=60)
    assert json.loads(read.stdout)["work_orders"][0]["id"] == created["id"]
