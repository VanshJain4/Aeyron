"""
Generate baseline features for test patients.
"""

import json
import os
import librosa

from detect import detect_coughs
from features import extract_features


def create_baselines():
    """Extract and store baseline features for each patient."""
    sr = 22050
    os.makedirs("baselines", exist_ok=True)

    patients = ["001", "002", "003"]

    for patient_id in patients:
        audio_path = f"audio/patient_{patient_id}.wav"
        if not os.path.exists(audio_path):
            print(f"⚠️  {audio_path} not found, skipping...")
            continue

        print(f"Processing patient {patient_id}...")

        # Load audio
        y, _ = librosa.load(audio_path, sr=sr)

        # Detect coughs
        cough_segments = detect_coughs(audio_path, sr=sr)
        print(f"  → Detected {len(cough_segments)} coughs")

        if not cough_segments:
            print(f"  ⚠️  No coughs detected, skipping baseline...")
            continue

        # Extract features
        features = extract_features(y, cough_segments, sr=sr)
        baseline = features["averaged"]

        # Remove std values for baseline storage
        baseline_clean = {k: v for k, v in baseline.items() if "_std" not in k}

        # Save baseline
        baseline_path = f"baselines/patient_{patient_id}.json"
        with open(baseline_path, "w") as f:
            json.dump(baseline_clean, f, indent=2)
        print(f"  → Saved baseline to {baseline_path}")
        print(f"     Features: {json.dumps(baseline_clean, indent=2)}")


if __name__ == "__main__":
    create_baselines()
