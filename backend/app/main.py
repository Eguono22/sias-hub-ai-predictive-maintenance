"""Simulator-backed predictive maintenance API. Scores are demo indicators."""
import os
import sqlite3
import json
import logging
import httpx
from .simulator import read_fleet
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Literal

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.ensemble import IsolationForest

MACHINE_NAMES = {"M-001": "Hydraulic press", "M-002": "CNC spindle", "M-003": "Conveyor drive", "M-004": "Air compressor"}
DB_PATH = os.getenv("DATABASE_PATH", "data/maintenance.db")


@contextmanager
def database():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS readings (id INTEGER PRIMARY KEY, machine_id TEXT, timestamp TEXT, temperature REAL, vibration REAL, pressure REAL, current REAL, risk REAL, status TEXT)")
    connection.execute("CREATE INDEX IF NOT EXISTS readings_machine ON readings(machine_id, id)")
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(readings)")}
    if "power" not in columns:
        connection.execute("ALTER TABLE readings ADD COLUMN power REAL")
    if "raw_sensors" not in columns:
        connection.execute("ALTER TABLE readings ADD COLUMN raw_sensors TEXT")
    connection.execute("CREATE TABLE IF NOT EXISTS machine_catalog (id TEXT PRIMARY KEY, name TEXT)")
    connection.execute("CREATE TABLE IF NOT EXISTS work_orders (id TEXT PRIMARY KEY, machine_id TEXT, title TEXT, status TEXT, created_at TEXT)")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def require_machine(machine_id):
    if machine_id in MACHINE_NAMES:
        return
    with database() as connection:
        found = connection.execute("SELECT id FROM machine_catalog WHERE id = ?", (machine_id,)).fetchone()
    if not found:
        raise HTTPException(status_code=404, detail="Machine not found")


app = FastAPI(title="SIAS Hub Predictive Maintenance", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","), allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])
BASE = np.array([65., 2., 7., 48.])
SCALE = np.array([5., .4, .4, 3.])
rng = np.random.default_rng(42)
model = IsolationForest(contamination=.05, random_state=42).fit(rng.normal(size=(2000, 4)))

class Reading(BaseModel):
    temperature: float = Field(ge=-40, le=250)
    vibration: float = Field(ge=0, le=100)
    pressure: float = Field(ge=0, le=50)
    current: float = Field(ge=0, le=500)


def assess(reading: Reading):
    z = (np.array([reading.temperature, reading.vibration, reading.pressure, reading.current]) - BASE) / SCALE
    faults = []
    if reading.temperature > 80: faults.append("Possible overheating")
    if reading.vibration > 3.5: faults.append("Possible bearing wear or misalignment")
    if reading.pressure < 6: faults.append("Possible pressure loss")
    if reading.current > 57: faults.append("Possible electrical overload")
    return assess_deviation(z, faults)


def assess_deviation(z, faults):
    # PyTorch computes normalized deviation; IsolationForest detects multivariate outliers.
    deviation = torch.tensor(z, dtype=torch.float32).abs()
    model_anomaly = bool(model.predict([z])[0] == -1)
    anomaly = model_anomaly or bool(deviation.max() >= 3.5)
    risk = round(float(torch.clamp(deviation.max() / 8 * 100, 0, 100)), 1)
    status = "critical" if risk >= 70 else "warning" if anomaly or faults or risk >= 35 else "healthy"
    return {"anomaly": anomaly, "model_anomaly": model_anomaly, "risk": risk, "status": status, "faults": faults,
            "recommendation": "Inspect machine promptly" if status == "critical" else "Schedule a diagnostic inspection" if status == "warning" else "Continue routine monitoring"}

@app.get("/health")
def health():
    return {"status": "ok", "model": "IsolationForest", "data_sources": ["local", "sias"], "sias_configured": bool(os.getenv("SIAS_SIMULATOR_URL"))}

@app.post("/api/predict")
def predict(reading: Reading):
    return assess(reading)

def record_machine(machine, timestamp):
    sensors = machine["sensors"]
    with database() as connection:
        connection.execute("INSERT OR REPLACE INTO machine_catalog VALUES (?, ?)", (machine["id"], machine["name"]))
        connection.execute("INSERT INTO readings (machine_id, timestamp, temperature, vibration, pressure, current, risk, status, power, raw_sensors) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (machine["id"], timestamp, sensors["temperature"], sensors["vibration"], sensors["pressure"], sensors.get("current"), machine["risk"], machine["status"], sensors.get("power"), json.dumps(machine.get("raw_sensors", sensors))))
        connection.execute("DELETE FROM readings WHERE machine_id = ? AND id NOT IN (SELECT id FROM readings WHERE machine_id = ? ORDER BY id DESC LIMIT 1000)", (machine["id"], machine["id"]))
        samples = connection.execute("SELECT timestamp, temperature FROM readings WHERE machine_id = ? ORDER BY id DESC LIMIT 24", (machine["id"],)).fetchall()[::-1]
    return {**machine, "temperature_history": [row["temperature"] for row in samples], "history_timestamps": [row["timestamp"] for row in samples]}


@app.get("/api/machines")
def machines(scenario: Literal["normal", "bearing", "overheating"] = "normal", source: Literal["local", "sias"] = "local"):
    timestamp = datetime.now(timezone.utc).isoformat()
    result = []
    if source == "sias":
        try:
            timestamp, fleet = read_fleet(scenario)
            for machine in fleet:
                z = machine.pop("z")
                faults = []
                for index, description in [(0, "Possible overheating"), (1, "Possible bearing wear or misalignment"), (2, "Possible pressure deviation"), (3, "Possible power instability")]:
                    if (z[index] > (1.5 if index == 0 else 2) if index in (0, 1) else abs(z[index]) > 3):
                        faults.append(description)
                result.append({**machine, **assess_deviation(z, faults)})
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            logging.getLogger(__name__).warning("SIAS simulator is unavailable or returned an invalid contract")
            raise HTTPException(status_code=503, detail="SIAS simulator unavailable. Check SIAS_SIMULATOR_URL and its API contract.") from None
    else:
        generator = np.random.default_rng()
        for i, (machine_id, name) in enumerate(MACHINE_NAMES.items()):
            values = BASE + generator.normal(size=4) * SCALE * .5
            if i == 1 and scenario == "bearing": values[1] = 5.8
            if i == 0 and scenario == "overheating": values[0] = 99
            reading = Reading(**dict(zip(["temperature", "vibration", "pressure", "current"], values)))
            result.append({"id": machine_id, "name": name, "line": "Production line 01", "sensors": reading.model_dump(), **assess(reading)})
    return {"timestamp": timestamp, "simulated": True, "data_source": source, "machines": [record_machine(machine, timestamp) for machine in result]}


@app.get("/api/machines/{machine_id}/history")
def machine_history(machine_id: str):
    require_machine(machine_id)
    with database() as connection:
        rows = connection.execute("SELECT timestamp, temperature, vibration, pressure, current, power, raw_sensors, risk, status FROM readings WHERE machine_id = ? ORDER BY id DESC LIMIT 1000", (machine_id,)).fetchall()
    return {"machine_id": machine_id, "readings": [dict(row) for row in reversed(rows)]}


class WorkOrder(BaseModel):
    machine_id: str
    title: str = Field(min_length=3, max_length=200)


class WorkOrderUpdate(BaseModel):
    status: Literal["open", "in_progress", "completed"]


@app.get("/api/work-orders")
def work_orders():
    with database() as connection:
        rows = connection.execute("SELECT * FROM work_orders ORDER BY created_at DESC").fetchall()
    return {"work_orders": [dict(row) for row in rows]}


@app.post("/api/work-orders", status_code=201)
def create_work_order(order: WorkOrder):
    require_machine(order.machine_id)
    title = order.title.strip()
    if len(title) < 3:
        raise HTTPException(status_code=422, detail="Title must contain at least 3 non-whitespace characters")
    record = {"id": str(uuid4()), "machine_id": order.machine_id, "title": title, "status": "open", "created_at": datetime.now(timezone.utc).isoformat()}
    with database() as connection:
        connection.execute("INSERT INTO work_orders VALUES (?, ?, ?, ?, ?)", tuple(record.values()))
    return record


@app.patch("/api/work-orders/{order_id}")
def update_work_order(order_id: str, update: WorkOrderUpdate):
    with database() as connection:
        cursor = connection.execute("UPDATE work_orders SET status = ? WHERE id = ?", (update.status, order_id))
        if not cursor.rowcount:
            raise HTTPException(status_code=404, detail="Work order not found")
        row = connection.execute("SELECT * FROM work_orders WHERE id = ?", (order_id,)).fetchone()
    return dict(row)
