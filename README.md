# SIAS Hub AI Predictive Maintenance

A Python-first predictive maintenance prototype with a FastAPI service and a Next.js + TypeScript dashboard at `/predictive-maintenance`.

Frontend deployment: https://sias-hub-ai-predictive-maintenance.vercel.app/predictive-maintenance. The hosted Python API is pending a Render/Railway connection; the deployed dashboard shows setup status until `NEXT_PUBLIC_API_URL` is configured.

## Run locally

Use Python 3.11+ and Node.js 20.9+.

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

In a second terminal:

```sh
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000/predictive-maintenance. API documentation: http://localhost:8000/docs.

## Capabilities

- Four local demo machines with temperature, vibration, pressure, and current readings.
- SIAS simulator integration with machine-specific baselines, original telemetry, and power in kW.
- Normal, bearing degradation, and overheating scenarios.
- Scikit-learn Isolation Forest trained on deterministic synthetic normal readings.
- PyTorch tensor operations compute a normalized deviation risk indicator; a 3.5-standard-deviation guard also flags extreme single-sensor readings.
- Sensor rules suggest potential faults and inspection actions.
- Dashboard refreshes every 15 seconds and supports machine selection.
- Persistent maintenance work orders with open, in-progress, and completed states.
- Recorded sensor history and bounded SQLite telemetry storage.

The dashboard supports the local demo and the SIAS Hub Industrial Machine Simulator. Set `SIAS_SIMULATOR_URL` in the Python service and select **SIAS Hub simulator** in the dashboard. The adapter reads `/machines` and `/fleet/telemetry`, normalizes against each machine’s baseline, and preserves power in kW separately from current in amps. The integration has been checked against the running local SIAS simulator. Machine variance uses explicit demo tolerances, not equipment-calibrated statistics. Charts show the last 24 recorded simulator snapshots; telemetry is persisted in SQLite, retaining 1,000 readings per machine. Sampling occurs when the fleet endpoint is requested, rather than through a background collector. Risk scores are heuristic indicators, not failure probabilities or remaining-life estimates. Fault diagnoses are rule-based hypotheses. The PyTorch component is not a trained neural network. Models and thresholds require validation against real equipment before operational use.

## API

- `GET /health`: service and model status.
- `GET /api/machines?scenario=normal`: simulated fleet assessment. Also accepts `bearing` and `overheating`. Add `source=sias` to read the external SIAS simulator (default: `source=local`).
- `POST /api/predict`: assess JSON fields `temperature` (°C), `vibration` (mm/s), `pressure` (bar), and `current` (A).

- `GET /api/machines/{machine_id}/history`: up to 1,000 recorded samples.
- `GET /api/work-orders`: list maintenance tasks.
- `POST /api/work-orders`: create a task with `machine_id` and `title`.
- `PATCH /api/work-orders/{id}`: set `status` to `open`, `in_progress`, or `completed`.

## Verify

```sh
cd backend
python -m pytest tests -q
```

```sh
cd frontend
npm run typecheck
npm run build
```

## Deployment

Import the repository into Vercel with **Root Directory** set to `frontend`. Set `NEXT_PUBLIC_API_URL` to the public HTTPS Python API URL before building.

Host `backend` separately using its Dockerfile or `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Set `CORS_ORIGINS` to the exact Vercel frontend origin (comma-separated if multiple). Environment example files are documentation; export backend variables through your shell or hosting provider. SQLite stores telemetry and work orders at `DATABASE_PATH` (default `data/maintenance.db` locally). Mount a persistent volume at `/data` for the Docker image. The API is an unauthenticated demo; add access control and model lifecycle management before exposing sensitive operational data. Use one API instance with SQLite.

See [deployment instructions](docs/deployment.md) for Vercel, Render, Railway, and Docker hosting. `render.yaml` defines a Render API service; `backend/railway.json` defines the Railway API build and health checks. Run the API with `docker compose up --build -d`; the named volume preserves records between container restarts. GitHub Actions validates both applications on pushes and pull requests.
