# AEYRON Sentinel — Vitals backend

FastAPI server for Presage-shaped vitals and vitals_risk. Used by the Sentinel dashboard.

## Setup

```bash
cd backend
python3 -m pip install -r requirements.txt
```

Set `PRESAGE_API_KEY` in the environment when using the real Presage SDK (see `.env.example`).

Optional face/emotion thresholds (defaults in parentheses):
- `EMOTION_VARIANCE_THRESHOLD` (0.04)
- `EMOTION_STD_THRESHOLD` (0.20)
- `EMOTION_ROLLING_WINDOW` (30)

## Run API

```bash
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- **POST /vitals** — body: `{ heart_rate, hrv, stress_score, patient }`. Stores values and returns `vitals_risk`.
- **GET /vitals** — returns latest vitals and `vitals_risk`.

## Optional: live emotions (more expression labels)

Install the FER library so the live bridge sends real emotions from your face:

```bash
pip install fer
```

Then run the live bridge as usual. It will detect and send: **angry**, **disgust**, **fear**, **happy**, **sad**, **surprise**, **neutral**. Without `fer`, only "neutral" is sent.

## Checking if vitals are correct

See [VALIDATION.md](VALIDATION.md) for how to check heart rate (manual pulse, watch) and breathing rate (count breaths).

## Run simulator (demo)

With the API running:

```bash
python3 presage_simulator.py A   # healthy
python3 presage_simulator.py B   # warning
python3 presage_simulator.py C   # critical
```

Optional: `--interval 2` (default 2 seconds between POSTs).
