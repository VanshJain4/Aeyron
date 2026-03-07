"""
Real-time voice detection for demo: mic stream → last 10 s → features + infer → live numbers.
"""
import numpy as np

from core.config import VULTR_BASE_URL, PATIENT_ID, UCI_PATIENT_ID, UCI_PD_PATIENT_ID
from core.live_buffer import LiveMicBuffer
from core.quick_test import extract_quick_features, features_to_vector
from core.acoustic_features import extract_features as extract_praat_features, uci_features_to_vector
from core import client_network

SAMPLE_RATE = 16000
CHUNK_SEC = 5.0
LIVE_BUFFER_SEC = 10.0
MIN_SAMPLES = int(LIVE_BUFFER_SEC * SAMPLE_RATE)

_buffer: LiveMicBuffer | None = None


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
    Lower MSE to a cohort = closer to that cohort. P(healthy) = mse_pd / (mse_h + mse_pd).
    """
    if mse_healthy + mse_pd <= 0:
        return 50.0
    return 100.0 * mse_pd / (mse_healthy + mse_pd)


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
        out_h = client_network.infer(VULTR_BASE_URL, UCI_PATIENT_ID, uci_vec)
        out_pd_resp = client_network.infer(VULTR_BASE_URL, UCI_PD_PATIENT_ID, uci_vec)

        mse_p = out_p.get("anomaly_score") or 0.0
        th_p = out_p.get("threshold") or 1e-9
        ratio_p = mse_p / th_p
        status_p = out_p.get("status", "—")
        risk_pct = _risk_flagged(ratio_p)

        mse_h = out_h.get("anomaly_score") or 0.0
        mse_pd = out_pd_resp.get("anomaly_score") or 0.0
        closer = "healthy" if mse_h <= mse_pd else "PD"
        p_healthy = _uci_p_healthy(mse_h, mse_pd)
        p_pd = 100.0 - p_healthy

        return (
            "### Personal (your baseline)\n\n"
            f"|  |  |\n|--|--|\n"
            f"| **MSE** | {mse_p:.4f} |\n"
            f"| **Threshold** | {th_p:.4f} |\n"
            f"| **Ratio** (MSE/threshold) | {ratio_p:.3f} |\n"
            f"| **Result** | **{status_p}** |\n"
            f"| **Risk %** (0%=normal, 100%=flagged) | **{risk_pct:.0f}%** |\n\n"
            "---\n\n"
            "### UCI (healthy vs PD)\n\n"
            f"|  |  |\n|--|--|\n"
            f"| **MSE vs healthy** | {mse_h:.4f} |\n"
            f"| **MSE vs PD** | {mse_pd:.4f} |\n"
            f"| **Closer to** | **{closer}** |\n"
            f"| **Healthy likelihood** | {p_healthy:.1f}% |\n"
            f"| **PD likelihood** | {p_pd:.1f}% |\n"
        )
    except Exception as e:
        return f"**Error:** {e}"
