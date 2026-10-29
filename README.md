# SIAS Hub AI Predictive Maintenance

A Python-first predictive maintenance prototype with a FastAPI service and a Next.js + TypeScript dashboard at `/predictive-maintenance`.

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

- Four simulated machines with temperature, vibration, pressure, and current readings.
- Normal, bearing degradation, and overheating scenarios.
- Scikit-learn Isolation Forest trained on deterministic synthetic normal readings.
- PyTorch tensor operations compute a normalized deviation risk indicator; a 3.5-standard-deviation guard also flags extreme single-sensor readings.
- Sensor rules suggest potential faults and inspection actions.
- Dashboard refreshes every 15 seconds and supports machine selection.

This repository includes a local simulator adapter, not a verified connection to an external SIAS Hub Industrial Machine Simulator. Replace the generator in `backend/app/main.py` with the actual simulator integration when its API contract is available. Charts contain generated samples for each snapshot, not persisted historical telemetry. Risk scores are heuristic indicators, not failure probabilities or remaining-life estimates. Fault diagnoses are rule-based hypotheses. The PyTorch component is not a trained neural network. Models and thresholds require validation against real equipment before operational use.

## API

- `GET /health`: service and model status.
- `GET /api/machines?scenario=normal`: simulated fleet assessment. Also accepts `bearing` and `overheating`.
- `POST /api/predict`: assess JSON fields `temperature` (°C), `vibration` (mm/s), `pressure` (bar), and `current` (A).

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

Host `backend` separately using its Dockerfile or `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Set `CORS_ORIGINS` to the exact Vercel frontend origin (comma-separated if multiple). Environment example files are documentation; export backend variables through your shell or hosting provider. The API is a stateless demo without authentication or durable storage. Add access control, telemetry storage, and model lifecycle management before production deployment.
