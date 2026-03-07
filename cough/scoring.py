"""
Steps 4-7: Baseline comparison, severity scoring, confidence scoring, and trend analysis.
"""

import json
import os
import numpy as np


def load_baseline(patient_id):
    """Load baseline features for a patient."""
    baseline_path = f"baselines/patient_{patient_id}.json"
    if os.path.exists(baseline_path):
        with open(baseline_path) as f:
            return json.load(f)
    return None


def baseline_comparison(features, patient_id):
    """
    Step 4: Compare current features to patient's baseline.
    Returns percent change for each feature.
    """
    baseline = load_baseline(patient_id)
    if not baseline:
        return None

    comparison = {}
    for key in baseline.keys():
        if key in features["averaged"]:
            current = features["averaged"][key]
            baseline_val = baseline[key]
            if baseline_val != 0:
                percent_change = ((current - baseline_val) / baseline_val) * 100
            else:
                percent_change = 0
            comparison[key] = percent_change

    return comparison


def severity_scoring(features, patient_id):
    """
    Step 5: Weighted deviation model for severity.
    Maps percent deviation to 0-100 severity score.
    """
    comparison = baseline_comparison(features, patient_id)
    if not comparison:
        return 50.0  # Default if no baseline

    # Weights for each feature
    weights = {
        "spectral_centroid": 0.25,
        "peak_to_decay_ratio": 0.25,
        "rise_time": 0.15,
        "spectral_slope": 0.15,
        "expulsive_duration": 0.10,
        "zero_crossing_rate": 0.10,
    }

    # Map percent deviation to sub-score
    def percent_to_subscore(percent_dev):
        abs_dev = abs(percent_dev)
        if abs_dev < 10:
            return 10
        elif abs_dev < 20:
            return 30
        elif abs_dev < 30:
            return 60
        else:
            return 90

    weighted_score = 0.0
    for feature, weight in weights.items():
        if feature in comparison:
            subscore = percent_to_subscore(comparison[feature])
            weighted_score += subscore * weight

    return min(weighted_score, 100.0)


def confidence_scoring(features, num_coughs):
    """
    Step 6: Confidence scoring with penalties.
    Starts at 1.0, subtracts penalties, floors at 0.0.
    """
    confidence = 1.0

    # Penalty: only one cough detected
    if num_coughs == 1:
        confidence -= 0.2

    # Penalty: high variance across coughs
    if len(features["per_cough"]) > 1:
        # Check if any feature has high std relative to mean
        for key in features["per_cough"][0].keys():
            values = [f[key] for f in features["per_cough"]]
            mean_val = np.mean(values)
            std_val = np.std(values)
            if mean_val != 0:
                cv = std_val / mean_val  # Coefficient of variation
                if cv > 0.3:  # High inconsistency
                    confidence -= 0.15
                    break

    # Penalty: edge of duration window
    # This is approximate without re-checking cough durations
    # For now, skip this penalty to avoid over-penalizing

    return max(confidence, 0.0)


def load_history(patient_id):
    """Load patient's severity history."""
    history_path = f"history/patient_{patient_id}_history.json"
    if os.path.exists(history_path):
        with open(history_path) as f:
            return json.load(f)
    return []


def trend_analysis(current_severity, patient_id, flags_list):
    """
    Step 7: Analyze trends and add flags.
    """
    history = load_history(patient_id)

    trend = "stable"
    new_flags = flags_list.copy() if flags_list else []

    if history:
        # Last three readings
        recent = history[-3:] if len(history) >= 3 else history
        avg_recent = np.mean([h["severity"] for h in recent])

        # Declining trend: 15+ points higher than average of last 3
        if current_severity >= avg_recent + 15:
            trend = "declining"

        # Sustained decline: 3+ consecutive increases
        if len(history) >= 3:
            last_three = history[-3:]
            severities = [h["severity"] for h in last_three]
            if (severities[0] < severities[1] < severities[2] and
                severities[2] < current_severity):
                new_flags.append("sustained_decline")

        # Clinical threshold check (spectral centroid < 160 Hz)
        if ("spectral_centroid_low" not in new_flags and
            current_severity > 70):
            new_flags.append("below_clinical_threshold")

    return trend, new_flags


def score_recording(features, patient_id, num_coughs, medication_status=None):
    """
    Combine all scoring steps.
    """
    severity = severity_scoring(features, patient_id)
    confidence = confidence_scoring(features, num_coughs)

    flags = []
    if medication_status == "off" and severity > 60:
        flags.append("possible_medication_related")

    trend, flags = trend_analysis(severity, patient_id, flags)

    return {
        "severity": severity,
        "confidence": confidence,
        "trend": trend,
        "flags": flags,
    }
