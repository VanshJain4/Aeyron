# AEYRON Sentinel — Vitals backend

FastAPI server for Presage-shaped vitals and vitals_risk. Used by the Sentinel dashboard.

## Setup

```bash
cd backend
pip install -r requirements.txt
```

Set `PRESAGE_API_KEY` in the environment when using the real Presage SDK (see `.env.example`).

## Run API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- **POST /vitals** — body: `{ heart_rate, hrv, stress_score, patient }`. Stores values and returns `vitals_risk`.
- **GET /vitals** — returns latest vitals and `vitals_risk`.

## Run simulator (demo)

With the API running:

```bash
python presage_simulator.py A   # healthy
python presage_simulator.py B   # warning
python presage_simulator.py C   # critical
```

Optional: `--interval 2` (default 2 seconds between POSTs).
