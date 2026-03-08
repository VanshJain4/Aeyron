"""
Extract and store baseline features for test patients from audio/patient_NNN.wav.
Run once after create_test_audio.py.
"""
from __future__ import annotations

import json
import librosa
from pathlib import Path

from detect import detect_coughs
from features import extract_features

_DIR = Path(__file__).resolve().parent


def create_baselines() -> None:
    baselines_dir = _DIR / "baselines"
    baselines_dir.mkdir(exist_ok=True)

    for pid in ("001", "002", "003"):
        audio_path = _DIR / "audio" / f"patient_{pid}.wav"
        if not audio_path.exists():
            print(f"  {audio_path} not found, skipping")
            continue

        print(f"Patient {pid}:")
        y, sr = librosa.load(str(audio_path), sr=22050)
        segments = detect_coughs(str(audio_path), sr=sr)
        print(f"  detected {len(segments)} coughs")

        if not segments:
            print("  no coughs — skipping baseline")
            continue

        feats = extract_features(y, segments, sr=sr)
        baseline = {k: v for k, v in feats["averaged"].items() if "_std" not in k}

        out = baselines_dir / f"patient_{pid}.json"
        out.write_text(json.dumps(baseline, indent=2))
        print(f"  baseline saved → {out}")
        for k, v in baseline.items():
            print(f"    {k}: {v:.6f}")


if __name__ == "__main__":
    create_baselines()
