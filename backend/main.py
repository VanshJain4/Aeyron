"""
AEYRON Sentinel — Vitals API.
POST /vitals: Presage-shaped vitals + optional breathing_rate + face/emotion.
GET /vitals: latest vitals, vitals_risk, breathing_rate, face emotion variance/std and thresholds.
"""
from typing import Optional, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from face_emotion import FaceEmotionBuffer, EMOTION_VARIANCE_THRESHOLD, EMOTION_STD_THRESHOLD

app = FastAPI(title="AEYRON Sentinel Vitals API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_store: Optional[dict] = None
_face_buffer: FaceEmotionBuffer = FaceEmotionBuffer()


@app.get("/")
def root():
    return {"message": "AEYRON Sentinel Vitals API", "endpoints": {"GET /vitals": "latest vitals", "POST /vitals": "submit vitals"}, "docs": "/docs"}


class FaceEmotionPayload(BaseModel):
    expression: str = "neutral"
    confidence: float = 0.0
    blinking: bool = False
    talking: bool = False


class VitalsPayload(BaseModel):
    heart_rate: Optional[float] = None
    hrv: Optional[float] = None
    stress_score: Optional[float] = None
    patient: str = "live"
    breathing_rate: Optional[float] = None
    face: Optional[FaceEmotionPayload] = None
    source: Optional[str] = None  # "sdk" | "bridge" | "simulator"


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


def compute_vitals_risk(heart_rate: Optional[float], hrv: Optional[float], stress_score: Optional[float]) -> Optional[float]:
    hr = heart_rate if heart_rate is not None else 0.0
    hrv_val = hrv if hrv is not None else 0.0
    stress = stress_score if stress_score is not None else 0.0
    hr_risk = _hr_risk(hr) if heart_rate is not None else 0.0
    hrv_risk = _hrv_risk(hrv_val) if hrv is not None else 0.0
    return round((hr_risk * 0.35) + (hrv_risk * 0.35) + (stress * 0.3), 4)


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
        "breathing_rate": payload.breathing_rate,
        "vitals_risk": vitals_risk,
        "source": payload.source,
    }
    if payload.face is not None:
        _face_buffer.push(payload.face.confidence)
        _store["face"] = {
            "expression": payload.face.expression,
            "confidence": payload.face.confidence,
            "blinking": payload.face.blinking,
            "talking": payload.face.talking,
        }
    return {"ok": True, "vitals_risk": _store["vitals_risk"]}


@app.get("/vitals")
def get_vitals() -> dict:
    if _store is None:
        return _empty_vitals()
    out = _store.copy()
    out.setdefault("face", None)
    out["face_emotion_variance"] = round(_face_buffer.variance, 4)
    out["face_emotion_std"] = round(_face_buffer.std, 4)
    out["face_emotion_variance_threshold"] = EMOTION_VARIANCE_THRESHOLD
    out["face_emotion_std_threshold"] = EMOTION_STD_THRESHOLD
    out["face_emotion_variance_breach"] = _face_buffer.variance_breach()
    out["face_emotion_std_breach"] = _face_buffer.std_breach()
    return out


def _empty_vitals() -> dict:
    return {
        "heart_rate": None,
        "hrv": None,
        "stress_score": None,
        "patient": None,
        "breathing_rate": None,
        "vitals_risk": None,
        "face": None,
        "source": None,
        "face_emotion_variance": None,
        "face_emotion_std": None,
        "face_emotion_variance_threshold": EMOTION_VARIANCE_THRESHOLD,
        "face_emotion_std_threshold": EMOTION_STD_THRESHOLD,
        "face_emotion_variance_breach": False,
        "face_emotion_std_breach": False,
    }
