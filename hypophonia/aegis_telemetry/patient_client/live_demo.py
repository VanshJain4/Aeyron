"""
Real-time voice detection for demo: mic stream → last 10 s → features + infer → live numbers.
Profiling: each tick appends one row to live_demo_profile.csv for later analysis.
"""
import csv
import traceback
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

from core.config import VULTR_BASE_URL, PATIENT_ID
from core.live_buffer import LiveMicBuffer
from core.quick_test import extract_quick_features, features_to_vector
from core.acoustic_features import extract_features as extract_praat_features, uci_features_to_vector
from core import client_network

_svm = None
_svm_scaler = None

def _get_svm():
    global _svm, _svm_scaler
    if _svm is None:
        import joblib
        model_dir = Path(__file__).resolve().parent / "core" / "models"
        _svm = joblib.load(model_dir / "local_svm.joblib")
        _svm_scaler = joblib.load(model_dir / "local_scaler.joblib")
    return _svm, _svm_scaler

SAMPLE_RATE = 16000
CHUNK_SEC = 5.0
LIVE_BUFFER_SEC = 10.0
MIN_SAMPLES = int(LIVE_BUFFER_SEC * SAMPLE_RATE)

PROFILE_LOG = Path(__file__).resolve().parent / "live_demo_profile.csv"
PROFILE_HEADER = (
    "timestamp_utc",
    "mse_personal", "th_personal", "ratio_personal", "status_personal", "risk_pct",
    "mse_healthy", "mse_pd", "closer", "p_healthy", "p_pd",
)

_buffer: LiveMicBuffer | None = None


def _log_tick(
    mse_p: float, th_p: float, ratio_p: float, status_p: str, risk_pct: float,
    mse_h: float, mse_pd: float, closer: str, p_healthy: float, p_pd: float,
) -> None:
    row = (
        datetime.now(timezone.utc).isoformat(),
        f"{mse_p:.6f}", f"{th_p:.6f}", f"{ratio_p:.6f}", status_p, f"{risk_pct:.2f}",
        f"{mse_h:.6f}", f"{mse_pd:.6f}", closer, f"{p_healthy:.2f}", f"{p_pd:.2f}",
    )
    file_exists = PROFILE_LOG.is_file()
    with open(PROFILE_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(PROFILE_HEADER)
        w.writerow(row)


def _get_buffer() -> LiveMicBuffer:
    global _buffer
    if _buffer is None:
        _buffer = LiveMicBuffer(max_seconds=20.0, sample_rate=SAMPLE_RATE)
    return _buffer


def start_listening() -> tuple[str, bool]:
    b = _get_buffer()
    if not b.is_running():
        b.start()
    return "Listening… speak now. Results update every 2 s.", True


def stop_listening() -> tuple[str, bool]:
    b = _get_buffer()
    if b.is_running():
        b.stop()
    return "Stopped.", False


def _risk_flagged(ratio: float) -> float:
    """
    Risk % (0–100%) from MSE/threshold ratio.
    Ratio < 0.5 → 0% (normal), ratio = 1 → 50%, ratio ≥ 1.5 → 100% (flagged).
    """
    if ratio is None or ratio < 0:
        return 0.0
    if ratio <= 0.5:
        return 0.0
    if ratio >= 1.5:
        return 100.0
    return 100.0 * (ratio - 0.5)  # linear 0.5→0%, 1.0→50%, 1.5→100%


def _uci_p_healthy(mse_healthy: float, mse_pd: float) -> float:
    """
    Relative likelihood healthy vs PD from reconstruction MSEs.
    Uses log-ratio sharpening: p = sigmoid(k * log(mse_pd / mse_healthy)).
    k=3 gives ~71% for ratio 1.35x healthy-side, ~97% for ratio 3x PD-side.
    """
    import math
    if mse_healthy <= 0 and mse_pd <= 0:
        return 50.0
    if mse_healthy <= 0:
        return 0.0
    if mse_pd <= 0:
        return 100.0
    k = 3.0
    log_ratio = k * math.log(mse_pd / mse_healthy)
    p = 1.0 / (1.0 + math.exp(-log_ratio))
    return 100.0 * p


def live_tick(running: bool) -> str:
    """Called every 2 s: if running, get last 10 s, run inference, return formatted numbers."""
    if not running:
        return "**Live demo stopped.** Click **Start** to speak and see real-time results."
    b = _get_buffer()
    if not b.is_running():
        return "Click **Start** to begin."
    samples = b.get_last_seconds(LIVE_BUFFER_SEC)
    if samples is None:
        sec = b.seconds_available()
        return f"**Collecting audio…** {sec:.1f} s (need {LIVE_BUFFER_SEC:.0f} s). Keep speaking."
    try:
        n = int(CHUNK_SEC * SAMPLE_RATE)
        chunk1, chunk2 = samples[:n], samples[n:MIN_SAMPLES]
        v1 = features_to_vector(extract_quick_features(chunk1, sr=SAMPLE_RATE))
        v2 = features_to_vector(extract_quick_features(chunk2, sr=SAMPLE_RATE))
        personal_vec = list(np.mean([v1, v2], axis=0))
        out_p = client_network.infer(VULTR_BASE_URL, PATIENT_ID, personal_vec)
        task_a = samples[:n]
        task_b = samples[n:MIN_SAMPLES]
        feats = extract_praat_features(task_a, task_b)
        uci_vec = uci_features_to_vector(feats)

        # Local SVM classifier (98.3% CV accuracy, trained on PD audio + healthy audio)
        svm, svm_scaler = _get_svm()
        uci_arr = svm_scaler.transform([uci_vec])
        proba = svm.predict_proba(uci_arr)[0]  # [p_healthy, p_pd]
        p_healthy = 100.0 * proba[0]
        p_pd = 100.0 * proba[1]
        closer = "healthy" if p_healthy >= p_pd else "PD"

        mse_p = out_p.get("anomaly_score") or 0.0
        th_p = out_p.get("threshold") or 1e-9
        ratio_p = mse_p / th_p
        status_p = out_p.get("status", "—")
        risk_pct = _risk_flagged(ratio_p)

        _log_tick(
            mse_p, th_p, ratio_p, status_p, risk_pct,
            p_healthy / 100.0, p_pd / 100.0, closer, p_healthy, p_pd,
        )

        uci_names = ("HNR (dB)", "Spectral Flatness", "MFCC2", "Voiced Fraction", "Energy CV")
        uci_rows = "\n".join(f"| {n} | {v:.4f} |" for n, v in zip(uci_names, uci_vec))
        personal_names = ("mean_energy_db", "energy_std_db", "spectral_centroid", "spectral_bw", "zcr")
        personal_rows = "\n".join(f"| {n} | {v:.4f} |" for n, v in zip(personal_names, personal_vec))
        return (
            "## LIVE — Voice Analysis\n\n"
            "### Voice features (last 10 s)\n\n"
            f"|  |  |\n|--|--|\n{uci_rows}\n\n"
            "### SVM Classification (98% accuracy)\n\n"
            f"|  |  |\n|--|--|\n"
            f"| **Result** | **{closer.upper()}** |\n"
            f"| Healthy probability | {p_healthy:.1f}% |\n"
            f"| PD probability | {p_pd:.1f}% |\n\n"
            "---\n\n"
            "### Personal baseline (librosa)\n\n"
            f"|  |  |\n|--|--|\n{personal_rows}\n"
            f"| MSE | {mse_p:.6f} |\n"
            f"| Threshold | {th_p:.6f} |\n"
            f"| Ratio | {ratio_p:.3f} |\n"
            f"| Result | **{status_p}** |\n"
            f"| Risk % | **{risk_pct:.0f}%** |\n"
        )
    except Exception as e:
        return f"**Error:** {e}\n\n```\n{traceback.format_exc()}\n```"
