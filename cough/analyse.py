"""
Step 8: Main entry point
Ties all modules together: detect -> features -> scoring -> output JSON
"""

import json
import os
import sys
from datetime import datetime

import librosa

from detect import detect_coughs
from features import extract_features
from scoring import score_recording, load_history


def analyze(audio_path, patient_id, medication_status=None):
    """
    Analyze a recording for cough weakness indicators.

    Args:
        audio_path: Path to audio file
        patient_id: Patient identifier (e.g., "001")
        medication_status: Optional, "on" or "off"

    Returns:
        Dict with analysis results
    """
    # Step 1: Load audio
    sr = 22050
    y, _ = librosa.load(audio_path, sr=sr)

    # Step 2: Detect coughs
    cough_segments = detect_coughs(audio_path, sr=sr)

    if not cough_segments:
        result = {
            "patient_id": patient_id,
            "timestamp": datetime.now().isoformat(),
            "status": "no_cough_detected",
            "severity": 0.0,
            "confidence": 0.0,
        }
        return result

    # Step 3: Extract features
    features = extract_features(y, cough_segments, sr=sr)

    # Step 4 & 5 & 6 & 7: Scoring
    scores = score_recording(
        features,
        patient_id,
        len(cough_segments),
        medication_status=medication_status,
    )

    # Assemble result JSON
    result = {
        "patient_id": patient_id,
        "timestamp": datetime.now().isoformat(),
        "status": "success",
        "num_coughs": len(cough_segments),
        "features": {
            "spectral_centroid": features["averaged"]["spectral_centroid"],
            "peak_to_decay_ratio": features["averaged"]["peak_to_decay_ratio"],
            "spectral_slope": features["averaged"]["spectral_slope"],
            "rise_time": features["averaged"]["rise_time"],
            "zero_crossing_rate": features["averaged"]["zero_crossing_rate"],
            "expulsive_duration": features["averaged"]["expulsive_duration"],
        },
        "severity": scores["severity"],
        "confidence": scores["confidence"],
        "trend": scores["trend"],
        "flags": scores["flags"],
        "medication_status": medication_status,
    }

    # Step 9: Write output JSON
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/patient_{patient_id}_result.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    # Step 10: Append to history
    history_dir = "history"
    os.makedirs(history_dir, exist_ok=True)
    history_path = f"{history_dir}/patient_{patient_id}_history.json"

    history = load_history(patient_id)
    history.append({
        "timestamp": result["timestamp"],
        "severity": scores["severity"],
        "confidence": scores["confidence"],
        "trend": scores["trend"],
    })

    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python analyse.py <audio_path> <patient_id> [medication_status]")
        sys.exit(1)

    audio_path = sys.argv[1]
    patient_id = sys.argv[2]
    medication_status = sys.argv[3] if len(sys.argv) > 3 else None

    result = analyze(audio_path, patient_id, medication_status)
    print(json.dumps(result, indent=2))
