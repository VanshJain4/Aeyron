"""
Main entry point: detect → features → PD likelihood → severity scoring → JSON output.

Usage:
    python analyse.py <audio_path> <patient_id> [medication_status]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import librosa

from detect import detect_coughs
from features import extract_features
from pd_classifier import pd_likelihood
from scoring import score_recording, load_history

_DIR = Path(__file__).resolve().parent


def analyze(
    audio_path: str,
    patient_id: str,
    medication_status: str | None = None,
) -> dict:
    """
    Full pipeline: load → detect → extract → score → PD likelihood → save.

    Returns result dict.
    """
    sr = 22050
    y, _ = librosa.load(audio_path, sr=sr)

    # Detect coughs
    cough_segments = detect_coughs(audio_path, sr=sr)

    if not cough_segments:
        result = {
            "patient_id": patient_id,
            "timestamp": datetime.now().isoformat(),
            "status": "no_cough_detected",
            "num_coughs": 0,
            "severity": 0.0,
            "confidence": 0.0,
            "pd_score": None,
            "pd_label": None,
            "trend": "unknown",
            "flags": ["no_cough_detected"],
            "medication_status": medication_status,
        }
        _save(result, patient_id)
        return result

    # Extract features
    feats = extract_features(y, cough_segments, sr=sr)

    # Scoring against personal baseline
    scores = score_recording(feats, patient_id, len(cough_segments), medication_status)

    # PD likelihood from cough acoustic characteristics
    pd_score, pd_label = pd_likelihood(feats["averaged"])

    result = {
        "patient_id": patient_id,
        "timestamp": datetime.now().isoformat(),
        "status": "success",
        "num_coughs": len(cough_segments),
        "features": {
            k: round(feats["averaged"][k], 6)
            for k in (
                "spectral_centroid",
                "peak_to_decay_ratio",
                "spectral_slope",
                "rise_time",
                "zero_crossing_rate",
                "expulsive_duration",
            )
        },
        "severity": scores["severity"],
        "confidence": scores["confidence"],
        "pd_score": pd_score,
        "pd_label": pd_label,
        "trend": scores["trend"],
        "flags": scores["flags"],
        "medication_status": medication_status,
    }

    _save(result, patient_id)
    return result


def _save(result: dict, patient_id: str) -> None:
    """Write output JSON and append to history."""
    out_dir = _DIR / "output"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"patient_{patient_id}_result.json").write_text(
        json.dumps(result, indent=2)
    )

    hist_dir = _DIR / "history"
    hist_dir.mkdir(exist_ok=True)
    history = load_history(patient_id)
    history.append({
        "timestamp": result["timestamp"],
        "severity": result["severity"],
        "confidence": result["confidence"],
        "pd_score": result.get("pd_score"),
        "pd_label": result.get("pd_label"),
        "trend": result["trend"],
    })
    (hist_dir / f"patient_{patient_id}_history.json").write_text(
        json.dumps(history, indent=2)
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python analyse.py <audio_path> <patient_id> [medication_status]")
        sys.exit(1)

    _audio = sys.argv[1]
    _pid = sys.argv[2]
    _med = sys.argv[3] if len(sys.argv) > 3 else None

    _result = analyze(_audio, _pid, _med)
    print(json.dumps(_result, indent=2))
