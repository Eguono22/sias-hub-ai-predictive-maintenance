"""Read the SIAS simulator contract; preserve original units and baselines."""
import math
import os
import time

import httpx

STARTED = time.monotonic()
SCENARIOS = {"normal": "normal", "bearing": "bearing_wear", "overheating": "heat_excess"}
FEATURES = ("temperature_c", "vibration_mm_s", "pressure_bar", "power_kw")


def read_fleet(scenario):
    origin = os.getenv("SIAS_SIMULATOR_URL", "").rstrip("/")
    if not origin.startswith(("https://", "http://")):
        raise ValueError("SIAS_SIMULATOR_URL must be configured")
    with httpx.Client(base_url=origin, timeout=10) as client:
        catalog_response = client.get("/machines")
        catalog_response.raise_for_status()
        catalog = catalog_response.json()["machines"]
        if not catalog:
            raise ValueError("Simulator catalog is empty")
        response = client.get("/fleet/telemetry", params={
            "target": catalog[0]["id"], "scenario": SCENARIOS[scenario],
            # Begin after five simulated minutes so progressive faults are visible.
            "start": 300 + int(time.monotonic() - STARTED), "count": 1,
        })
        response.raise_for_status()
        sample = response.json()["samples"][-1]
    readings = {row["machine_id"]: row for row in sample["readings"]}
    result = []
    for machine in catalog:
        row = readings[machine["id"]]
        values = [float(row[key]) for key in FEATURES]
        baselines = [float(machine["baseline"][key]) for key in FEATURES]
        if not all(math.isfinite(v) for v in values + baselines) or any(v <= 0 for v in baselines):
            raise ValueError("Invalid simulator sensor values or baselines")
        # Engineering tolerances are demo assumptions, not learned equipment variance.
        scales = [max(abs(b) * ratio, floor) for b, ratio, floor in zip(baselines, (.05, .20, .05, .05), (2., .2, .2, 1.))]
        result.append({"id": machine["id"], "name": machine["name"], "line": machine.get("line", "SIAS Hub"),
                       "sensors": {"temperature": values[0], "vibration": values[1], "pressure": values[2], "current": None, "power": values[3]},
                       "baseline": dict(zip(FEATURES, baselines)), "raw_sensors": row,
                       "z": [(v-b)/scale for v,b,scale in zip(values, baselines, scales)]})
    return sample["timestamp"], result
