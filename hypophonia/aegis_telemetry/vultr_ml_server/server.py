"""
FastAPI server on 0.0.0.0:8000. Enroll (train), infer (MSE anomaly), history for dashboard.
Voice-only: 5 features. CUDA if available.
"""
import json
from pathlib import Path

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models.autoencoder import Autoencoder

app = FastAPI(title="Aegis Hypophonia ML")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SAVED_WEIGHTS_DIR = Path(__file__).resolve().parent / "saved_weights"
SAVED_WEIGHTS_DIR.mkdir(exist_ok=True)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
INPUT_DIM = 5
EPOCHS = 150
LR = 0.01
ANOMALY_THRESHOLD_MULTIPLIER = 6.0  # fallback if no threshold in meta
FEATURE_NAMES = [
    "mean_energy_db", "energy_std_db", "spectral_centroid_mean",
    "spectral_bandwidth_mean", "zero_crossing_mean",
]


class EnrollRequest(BaseModel):
    patient_id: str
    baseline_data: list[list[float]]  # N chunks x 5 features (e.g. from ~3 min audio)


class InferRequest(BaseModel):
    patient_id: str
    current_data: list[float]  # 5 features


def _minmax_scale(data: np.ndarray, min_vals: np.ndarray, max_vals: np.ndarray) -> np.ndarray:
    span = max_vals - min_vals
    span[span == 0] = 1.0
    return (data - min_vals) / span


def _fit_scaler(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    min_vals = data.min(axis=0)
    max_vals = data.max(axis=0)
    return min_vals, max_vals


MIN_BASELINE_CHUNKS = 10

@app.post("/api/enroll")
def enroll(req: EnrollRequest):
    if len(req.baseline_data) < MIN_BASELINE_CHUNKS or any(len(r) != INPUT_DIM for r in req.baseline_data):
        raise HTTPException(
            400,
            f"baseline_data must be at least {MIN_BASELINE_CHUNKS} arrays of {INPUT_DIM} floats each",
        )
    data = np.array(req.baseline_data, dtype=np.float64)
    min_vals, max_vals = _fit_scaler(data)
    scaled = _minmax_scale(data, min_vals, max_vals)
    scaled_t = torch.from_numpy(scaled.astype(np.float32)).to(DEVICE)

    model = Autoencoder().to(DEVICE)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    for _ in range(EPOCHS):
        opt.zero_grad()
        out = model(scaled_t)
        loss = torch.nn.functional.mse_loss(out, scaled_t)
        loss.backward()
        opt.step()

    with torch.no_grad():
        recon_all = model(scaled_t)
        baseline_loss = torch.nn.functional.mse_loss(recon_all, scaled_t).item()
        per_sample_mse = torch.nn.functional.mse_loss(recon_all, scaled_t, reduction="none").mean(dim=1)
        mse_np = per_sample_mse.cpu().numpy()
        # 90th percentile — relaxed so protocol-mismatched good voice can be "within normal"
        threshold = float(np.percentile(mse_np, 90))
    patient_id = req.patient_id.strip()
    if not patient_id:
        raise HTTPException(400, "patient_id required")
    pt_path = SAVED_WEIGHTS_DIR / f"{patient_id}.pt"
    meta_path = SAVED_WEIGHTS_DIR / f"{patient_id}_meta.json"
    torch.save(model.state_dict(), pt_path)
    meta_path.write_text(json.dumps({
        "min": min_vals.tolist(),
        "max": max_vals.tolist(),
        "baseline_loss": baseline_loss,
        "threshold": threshold,
    }))

    return {"status": "Model trained successfully", "baseline_loss": baseline_loss, "threshold": threshold}


@app.post("/api/infer")
def infer(req: InferRequest):
    if len(req.current_data) != INPUT_DIM:
        raise HTTPException(400, "current_data must be 5 floats")
    patient_id = req.patient_id.strip()
    if not patient_id:
        raise HTTPException(400, "patient_id required")
    pt_path = SAVED_WEIGHTS_DIR / f"{patient_id}.pt"
    meta_path = SAVED_WEIGHTS_DIR / f"{patient_id}_meta.json"
    if not pt_path.exists() or not meta_path.exists():
        raise HTTPException(404, "Patient not enrolled; run enroll first")

    meta = json.loads(meta_path.read_text())
    min_vals = np.array(meta["min"], dtype=np.float64)
    max_vals = np.array(meta["max"], dtype=np.float64)
    threshold = meta.get("threshold")
    if threshold is None:
        threshold = ANOMALY_THRESHOLD_MULTIPLIER * meta["baseline_loss"]
    data = np.array([req.current_data], dtype=np.float64)
    scaled = _minmax_scale(data, min_vals, max_vals)
    scaled = np.clip(scaled, 0.0, 1.0)
    x = torch.from_numpy(scaled.astype(np.float32)).to(DEVICE)

    model = Autoencoder().to(DEVICE)
    model.load_state_dict(torch.load(pt_path, map_location=DEVICE))
    model.eval()
    with torch.no_grad():
        recon = model(x)
        mse = torch.nn.functional.mse_loss(recon, x).item()

    status = "flagged" if mse > threshold else "normal"
    _record_infer(patient_id, mse, status)
    return {
        "anomaly_score": mse,
        "status": status,
        "threshold": threshold,
        "features_sent": dict(zip(FEATURE_NAMES, [float(x) for x in req.current_data])),
    }


@app.get("/api/profile/{patient_id}")
def get_profile(patient_id: str):
    """What the trained model has: threshold, scaler range, baseline loss."""
    patient_id = patient_id.strip()
    meta_path = SAVED_WEIGHTS_DIR / f"{patient_id}_meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Patient not enrolled")
    meta = json.loads(meta_path.read_text())
    return {
        "patient_id": patient_id,
        "threshold": meta.get("threshold"),
        "baseline_loss": meta.get("baseline_loss"),
        "scaler_min": dict(zip(FEATURE_NAMES, meta["min"])),
        "scaler_max": dict(zip(FEATURE_NAMES, meta["max"])),
    }


_history: dict[str, list[dict]] = {}


def _record_infer(patient_id: str, anomaly_score: float, status: str) -> None:
    _history.setdefault(patient_id, []).append({"anomaly_score": anomaly_score, "status": status})


@app.get("/api/history/{patient_id}")
def get_history(patient_id: str):
    return _history.get(patient_id.strip(), [])
