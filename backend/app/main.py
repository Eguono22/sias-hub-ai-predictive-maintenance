"""Simulator-backed predictive maintenance API. Scores are demo indicators."""
import os
from datetime import datetime, timezone
from typing import Literal

import numpy as np
import torch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.ensemble import IsolationForest

app = FastAPI(title="SIAS Hub Predictive Maintenance", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
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
    # PyTorch computes normalized deviation; IsolationForest detects multivariate outliers.
    deviation = torch.tensor(z, dtype=torch.float32).abs()
    model_anomaly = bool(model.predict([z])[0] == -1)
    anomaly = model_anomaly or bool(deviation.max() >= 3.5)
    risk = round(float(torch.clamp(deviation.max() / 8 * 100, 0, 100)), 1)
    faults = []
    if reading.temperature > 80: faults.append("Possible overheating")
    if reading.vibration > 3.5: faults.append("Possible bearing wear or misalignment")
    if reading.pressure < 6: faults.append("Possible pressure loss")
    if reading.current > 57: faults.append("Possible electrical overload")
    status = "critical" if risk >= 70 else "warning" if anomaly or risk >= 35 else "healthy"
    return {"anomaly": anomaly, "model_anomaly": model_anomaly, "risk": risk, "status": status, "faults": faults,
            "recommendation": "Inspect machine promptly" if status == "critical" else "Schedule a diagnostic inspection" if status == "warning" else "Continue routine monitoring"}

@app.get("/health")
def health():
    return {"status": "ok", "model": "IsolationForest", "data_source": "local simulator"}

@app.post("/api/predict")
def predict(reading: Reading):
    return assess(reading)

@app.get("/api/machines")
def machines(scenario: Literal["normal", "bearing", "overheating"] = "normal"):
    generator = np.random.default_rng()
    result = []
    for i, name in enumerate(["Hydraulic press", "CNC spindle", "Conveyor drive", "Air compressor"]):
        values = BASE + generator.normal(size=4) * SCALE * .5
        if i == 1 and scenario == "bearing": values[1] = 5.8
        if i == 0 and scenario == "overheating": values[0] = 99
        reading = Reading(**dict(zip(["temperature", "vibration", "pressure", "current"], values)))
        history = [round(float(v), 2) for v in generator.normal(values[0], 1.2, 24)]
        result.append({"id": f"M-{i+1:03}", "name": name, "sensors": reading.model_dump(), "temperature_history": history, **assess(reading)})
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "simulated": True, "machines": result}
