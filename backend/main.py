"""
AEYRON Sentinel — Vitals API.
POST /vitals: Presage-shaped vitals + optional breathing_rate + face/emotion.
GET /vitals: latest vitals, vitals_risk, breathing_rate, face emotion variance/std and thresholds.
POST /voice: voice PD telemetry from hypophonia pipeline.
POST /cough: cough PD telemetry.
GET /status: unified multi-modal PD risk view.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, List

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
_voice_store: Optional[dict] = None
_cough_store: Optional[dict] = None


@app.get("/")
def root():
    return {
        "message": "AEYRON Sentinel Vitals API",
        "endpoints": {
            "GET /vitals": "latest vitals",
            "POST /vitals": "submit vitals",
            "POST /voice": "submit voice PD telemetry",
            "GET /voice": "latest voice data",
            "POST /cough": "submit cough PD telemetry",
            "GET /cough": "latest cough data",
            "GET /status": "unified multi-modal PD risk view",
        },
        "docs": "/docs",
    }


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


# --------------- Voice modality ---------------

class VoicePayload(BaseModel):
    pd_probability: float
    svm_confidence: float
    features: Dict = {}
    source: str = "unknown"


@app.post("/voice")
def post_voice(payload: VoicePayload) -> dict:
    global _voice_store
    _voice_store = {
        "pd_probability": payload.pd_probability,
        "svm_confidence": payload.svm_confidence,
        "features": payload.features,
        "source": payload.source,
        "last_update": datetime.now(timezone.utc).isoformat(),
    }
    return {"ok": True, "pd_probability": payload.pd_probability}


@app.get("/voice")
def get_voice() -> dict:
    if _voice_store is None:
        return {"pd_probability": None, "svm_confidence": None, "features": {}, "source": None, "last_update": None}
    return _voice_store


# --------------- Cough modality ---------------

class CoughPayload(BaseModel):
    pd_score: float
    pd_label: str
    num_coughs: int
    features: Dict = {}


@app.post("/cough")
def post_cough(payload: CoughPayload) -> dict:
    global _cough_store
    _cough_store = {
        "pd_score": payload.pd_score,
        "pd_label": payload.pd_label,
        "num_coughs": payload.num_coughs,
        "features": payload.features,
        "last_update": datetime.now(timezone.utc).isoformat(),
    }
    return {"ok": True, "pd_score": payload.pd_score}


@app.get("/cough")
def get_cough() -> dict:
    if _cough_store is None:
        return {"pd_score": None, "pd_label": None, "num_coughs": None, "features": {}, "last_update": None}
    return _cough_store


# --------------- Unified status ---------------

def _compute_combined_pd_score(
    voice_prob: Optional[float],
    heart_risk: Optional[float],
    cough_score: Optional[float],
    face_hypomimia: Optional[float],
) -> tuple:
    """Return (combined_score, combined_label, active_modalities).

    Weights: voice 0.30, heart 0.25, cough 0.25, face 0.20.
    Only modalities that have received data are included; weights are
    renormalized so they still sum to 1.
    """
    weights = {
        "voice": 0.30,
        "heart": 0.25,
        "cough": 0.25,
        "face": 0.20,
    }
    scores = {}
    if voice_prob is not None:
        scores["voice"] = voice_prob
    if heart_risk is not None:
        scores["heart"] = heart_risk
    if cough_score is not None:
        scores["cough"] = cough_score
    if face_hypomimia is not None:
        scores["face"] = face_hypomimia

    active = list(scores.keys())
    if not active:
        return None, "NO_DATA", active

    total_weight = sum(weights[m] for m in active)
    combined = sum(weights[m] * scores[m] / total_weight for m in active)
    combined = round(combined, 4)

    if combined >= 0.60:
        label = "HIGH_RISK"
    elif combined >= 0.35:
        label = "MODERATE_RISK"
    else:
        label = "LOW_RISK"

    return combined, label, active


@app.get("/status")
def get_status() -> dict:
    # --- heart ---
    heart: dict
    heart_risk_val: Optional[float] = None
    if _store is not None:
        heart = {
            "hr": _store.get("heart_rate"),
            "br": _store.get("breathing_rate"),
            "vitals_risk": _store.get("vitals_risk"),
            "source": _store.get("source"),
        }
        heart_risk_val = _store.get("vitals_risk")
    else:
        heart = {"hr": None, "br": None, "vitals_risk": None, "source": None}

    # --- voice ---
    voice: dict
    voice_prob: Optional[float] = None
    if _voice_store is not None:
        voice = {
            "pd_probability": _voice_store["pd_probability"],
            "svm_confidence": _voice_store["svm_confidence"],
            "last_update": _voice_store["last_update"],
        }
        voice_prob = _voice_store["pd_probability"]
    else:
        voice = {"pd_probability": None, "svm_confidence": None, "last_update": None}

    # --- cough ---
    cough: dict
    cough_score: Optional[float] = None
    if _cough_store is not None:
        cough = {
            "pd_score": _cough_store["pd_score"],
            "pd_label": _cough_store["pd_label"],
            "num_coughs": _cough_store["num_coughs"],
            "last_update": _cough_store["last_update"],
        }
        cough_score = _cough_store["pd_score"]
    else:
        cough = {"pd_score": None, "pd_label": None, "num_coughs": None, "last_update": None}

    # --- face ---
    face: dict
    face_hypo: Optional[float] = None
    has_face = _store is not None and _store.get("face") is not None
    if has_face:
        var = round(_face_buffer.variance, 4)
        std = round(_face_buffer.std, 4)
        hypomimia_detected = _face_buffer.variance_breach() or _face_buffer.std_breach()
        face = {
            "variance": var,
            "std": std,
            "hypomimia_detected": hypomimia_detected,
            "blinking": _store["face"].get("blinking", False),
            "talking": _store["face"].get("talking", False),
        }
        # Map hypomimia flag to a 0-1 score for the combined calculation
        face_hypo = 1.0 if hypomimia_detected else 0.0
    else:
        face = {"variance": None, "std": None, "hypomimia_detected": None, "blinking": None, "talking": None}

    combined_score, combined_label, active = _compute_combined_pd_score(
        voice_prob, heart_risk_val, cough_score, face_hypo,
    )

    return {
        "heart": heart,
        "voice": voice,
        "cough": cough,
        "face": face,
        "combined_pd_score": combined_score,
        "combined_label": combined_label,
        "active_modalities": active,
    }
