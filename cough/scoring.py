"""
Baseline comparison, severity scoring, confidence scoring, and trend analysis.
"""
from __future__ import annotations

import json
import numpy as np
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def load_baseline(patient_id: str) -> dict | None:
    """Load baseline features for a patient."""
    path = _DIR / "baselines" / f"patient_{patient_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def baseline_comparison(features: dict, patient_id: str) -> dict | None:
    """
    Compare current averaged features to patient's stored baseline.
    Returns percent change per feature (positive = increased from baseline).
    """
    baseline = load_baseline(patient_id)
    if not baseline:
        return None

    comparison = {}
    for key, baseline_val in baseline.items():
        if key in features["averaged"]:
            current = features["averaged"][key]
            if baseline_val != 0:
                comparison[key] = ((current - baseline_val) / abs(baseline_val)) * 100.0
            else:
                comparison[key] = 0.0
    return comparison


def severity_scoring(features: dict, patient_id: str) -> float:
    """
    Weighted deviation from personal baseline → severity score 0–100.
    """
    comparison = baseline_comparison(features, patient_id)
    if not comparison:
        return 50.0  # No baseline: return neutral

    weights = {
        "spectral_centroid": 0.25,
        "peak_to_decay_ratio": 0.25,
        "rise_time": 0.15,
        "spectral_slope": 0.15,
        "expulsive_duration": 0.10,
        "zero_crossing_rate": 0.10,
    }

    def _subscore(pct: float) -> float:
        """Map |percent deviation| to a 0-100 sub-score."""
        a = abs(pct)
        if a < 10:
            return 10.0
        elif a < 20:
            return 30.0
        elif a < 40:
            return 60.0
        else:
            return 90.0

    weighted = 0.0
    for feat, w in weights.items():
        if feat in comparison:
            weighted += _subscore(comparison[feat]) * w

    return min(weighted, 100.0)


def confidence_scoring(features: dict, num_coughs: int) -> float:
    """
    Confidence score 0–1. Penalises low cough count and high inter-cough variance.
    """
    conf = 1.0

    if num_coughs == 0:
        return 0.0
    if num_coughs == 1:
        conf -= 0.20

    if len(features.get("per_cough", [])) > 1:
        for key in features["per_cough"][0]:
            vals = [f[key] for f in features["per_cough"]]
            mean_v = float(np.mean(vals))
            std_v = float(np.std(vals))
            if mean_v != 0 and (std_v / abs(mean_v)) > 0.30:
                conf -= 0.15
                break

    return max(0.0, conf)


def load_history(patient_id: str) -> list:
    """Load patient severity history."""
    path = _DIR / "history" / f"patient_{patient_id}_history.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


def trend_analysis(current_severity: float, patient_id: str, flags: list) -> tuple[str, list]:
    """Detect trend from history and append new flags."""
    history = load_history(patient_id)
    trend = "stable"
    new_flags = list(flags)

    if history:
        recent = history[-3:] if len(history) >= 3 else history
        avg_recent = float(np.mean([h["severity"] for h in recent]))

        if current_severity >= avg_recent + 15:
            trend = "declining"

        if len(history) >= 3:
            sevs = [h["severity"] for h in history[-3:]]
            if sevs[0] < sevs[1] < sevs[2] < current_severity:
                if "sustained_decline" not in new_flags:
                    new_flags.append("sustained_decline")

        if current_severity > 70 and "below_clinical_threshold" not in new_flags:
            new_flags.append("below_clinical_threshold")

    return trend, new_flags


def score_recording(
    features: dict,
    patient_id: str,
    num_coughs: int,
    medication_status: str | None = None,
) -> dict:
    """Run all scoring steps and return combined result."""
    severity = severity_scoring(features, patient_id)
    confidence = confidence_scoring(features, num_coughs)

    flags: list[str] = []
    if medication_status == "off" and severity > 60:
        flags.append("possible_medication_related")

    trend, flags = trend_analysis(severity, patient_id, flags)

    return {
        "severity": round(severity, 2),
        "confidence": round(confidence, 2),
        "trend": trend,
        "flags": flags,
    }
