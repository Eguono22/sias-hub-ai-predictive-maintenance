# Deployment runbook

## Current deployment

The frontend is deployed at https://sias-hub-ai-predictive-maintenance.vercel.app/predictive-maintenance. The Python API is not yet deployed because Render/Railway account access is not connected. The frontend intentionally displays setup status until its API origin is configured. Vercel deployment protection is enabled by the account's project settings.

When an API host is connected, deploy its prepared configuration with `CORS_ORIGINS=https://sias-hub-ai-predictive-maintenance.vercel.app`. Set the simulator's publicly reachable origin in `SIAS_SIMULATOR_URL`. Then set Vercel's `NEXT_PUBLIC_API_URL` to the new API origin and redeploy the frontend. Do not use the local `127.0.0.1` API address for the hosted frontend.

Local verification includes normal/bearing/overheating scenarios against the running SIAS simulator and persistence across separate Python processes. Hosted API restart and CORS verification remain pending deployment.

## Python API

Build `backend/Dockerfile` with `backend` as its build context. The container accepts `PORT` (default 8000) and provides `/health` for health checks.

Set environment variables in the hosting provider:

- `CORS_ORIGINS`: exact frontend origin, e.g. `https://your-dashboard.vercel.app`. Multiple origins are comma-separated. Avoid a trailing slash.
- `DATABASE_PATH`: `/data/maintenance.db`.
- `PORT`: the port required by your host.

Attach a persistent volume at `/data`, writable by the container's `appuser`. Use a single instance with this SQLite setup. Disk persistence and volume permissions must be verified on the selected provider. Back up the SQLite database before replacing storage.

For a local container:

```sh
docker compose up --build -d
curl --fail http://localhost:8000/health
```

## Render

Create a Blueprint from this repository and select the root `render.yaml`. Review the paid `1c-2g` compute plan and 1 GB disk before applying it. The blueprint uses native Python 3.11, CPU-only PyTorch, a single instance, `/health`, and persistent SQLite storage at `/var/data/maintenance.db`. Enter the final frontend origin when prompted for `CORS_ORIGINS`.

After the service starts, record its HTTPS URL, run the smoke checks below, and use that URL for Vercel's `NEXT_PUBLIC_API_URL`.

## Railway

Create an API service from this repository with Root Directory `/backend` and Config File `/backend/railway.json`. The config uses the backend Dockerfile, one replica, a `/health` startup check, and bounded restart retries.

Attach a volume at `/data`, and configure these service variables before deployment:

```text
DATABASE_PATH=/data/maintenance.db
CORS_ORIGINS=https://your-dashboard.vercel.app
RAILWAY_RUN_UID=0
```

Railway mounts volumes as root; its documented `RAILWAY_RUN_UID=0` setting enables writes for this image's mounted database directory. This overrides the Dockerfile's non-root user on Railway. The standard Docker setup continues to use `appuser`. Generate a public HTTPS domain for the API, verify `/health`, and use the origin for Vercel's API URL.

## Using multiple API hosts

Render, Railway, and Docker deployments each own separate SQLite databases. They do not synchronize telemetry or work orders. Configure each Vercel environment with one API origin. Switching it changes which database the dashboard uses; it does not migrate records. Sharing records across hosts requires moving storage to a shared database before operating them as interchangeable replicas.

## Vercel frontend

Import the GitHub repository, choose the Next.js framework, and set Root Directory to `frontend`. `frontend/vercel.json` configures dependency installation and build commands. Set `NEXT_PUBLIC_API_URL` to the API's HTTPS origin with no trailing slash. Redeploy after changing this variable because Next.js embeds it during the build.

Configure the API's `CORS_ORIGINS` with the final Vercel origin. Preview deployments need their own allowed origins. Do not put API secrets in `NEXT_PUBLIC_` variables.

## Smoke test

1. Request `/health` on the hosted API.
2. Open `/predictive-maintenance` on the hosted frontend.
3. Choose bearing degradation and verify M-002 is marked critical.
4. Schedule an inspection, reload, and verify the work order persists.
5. Move it to in progress and then completed.
6. Restart the API and verify both work orders and machine history remain.
7. Switch back to normal operation and check that new snapshots appear in the chart.

The API has no authentication. Use a restricted demo environment until access controls are implemented. CORS controls browser access; it does not authenticate API clients. For the SIAS data source, set `SIAS_SIMULATOR_URL` in the hosted API to a reachable simulator API origin, then select SIAS Hub simulator in the dashboard. A cloud service cannot reach your laptop’s loopback address.

References: [Vercel project settings](https://vercel.com/docs/project-configuration/project-settings), [Render Blueprint reference](https://render.com/docs/blueprint-spec), [Railway config reference](https://docs.railway.com/config-as-code/reference), [Railway monorepos](https://docs.railway.com/deployments/monorepo), [Railway volumes](https://docs.railway.com/volumes).

## Local environment note

During development, ports 8000 and 8001 were already occupied. The predictive maintenance API was started on port 8015, and the dashboard used `NEXT_PUBLIC_API_URL=http://127.0.0.1:8015`. To reproduce:

```sh
# From backend, with its environment activated:
uvicorn app.main:app --host 127.0.0.1 --port 8015
# In another terminal, from frontend:
NEXT_PUBLIC_API_URL=http://127.0.0.1:8015 npm run dev -- --hostname 127.0.0.1
```

A running SIAS simulator was identified on port 8001. Its `/machines` catalog and `/fleet/telemetry` endpoint expose per-machine baselines, temperature in °C, vibration in mm/s, pressure in bar, and power in kW. The prototype uses current in amps and different operating ranges. Integration must introduce machine-specific normalization and an explicit power feature instead of treating kW as amps. The adapter is implemented in `backend/app/simulator.py`; it keeps kW separate from amps and uses asset-specific baselines. It is verified against the local simulator. Normalization tolerances are heuristic (5% for temperature, pressure, power; 20% for vibration, with lower bounds). Fault hints use positive temperature deviation above 1.5 normalized units, vibration above 2, and absolute pressure or power deviation above 3. The normalized Isolation Forest model is still trained on synthetic normal data. Fault scenarios begin at five simulated minutes so progressive degradation is observable.
