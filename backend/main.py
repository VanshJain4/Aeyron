"""
AEYRON Sentinel — Vitals API.
POST /vitals receives Presage-shaped vitals; GET /vitals returns latest + vitals_risk.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="AEYRON Sentinel Vitals API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for latest vitals (single patient / demo)
_store: dict | None = None


class VitalsPayload(BaseModel):
    heart_rate: float
    hrv: float
    stress_score: float
    patient: str


def _hr_risk(hr: float) -> float:
    if hr > 100 or hr < 55:
        return 1.0
    if hr > 90:
        return 0.6
    return 0.0


def _hrv_risk(hrv: float) -> float:
    if hrv < 15:
        return 1.0
    if hrv < 25:
        return 0.6
    return 0.0


def compute_vitals_risk(heart_rate: float, hrv: float, stress_score: float) -> float:
    hr_risk = _hr_risk(heart_rate)
    hrv_risk = _hrv_risk(hrv)
    return (hr_risk * 0.35) + (hrv_risk * 0.35) + (stress_score * 0.3)


@app.post("/vitals")
def post_vitals(payload: VitalsPayload) -> dict:
    global _store
    vitals_risk = compute_vitals_risk(
        payload.heart_rate, payload.hrv, payload.stress_score
    )
    _store = {
        "heart_rate": payload.heart_rate,
        "hrv": payload.hrv,
        "stress_score": payload.stress_score,
        "patient": payload.patient,
        "vitals_risk": round(vitals_risk, 4),
    }
    return {"ok": True, "vitals_risk": _store["vitals_risk"]}


@app.get("/vitals")
def get_vitals() -> dict:
    if _store is None:
        return {
            "heart_rate": None,
            "hrv": None,
            "stress_score": None,
            "patient": None,
            "vitals_risk": None,
        }
    return _store.copy()
