"""
Test trend detection: simulate three follow-up recordings for patient_001
showing progressive cough decline, and verify the trend flags fire.
"""
from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from scipy.io import wavfile

from create_test_audio import _cough_healthy, _cough_moderate, _cough_severe_pd, RNG
from analyse import analyze

_DIR = Path(__file__).resolve().parent


def _make_recording(cough_fn, sr: int = 22050, num_coughs: int = 3) -> np.ndarray:
    silence = np.zeros(int(sr * 0.5))
    gap = np.zeros(int(sr * 0.35))
    parts = [silence]
    for _ in range(num_coughs):
        c = cough_fn(sr=sr)
        peak = np.max(np.abs(c))
        if peak > 0:
            c = c / peak * 0.85
        parts += [c, gap]
    rec = np.concatenate(parts)
    rec += 0.008 * RNG.standard_normal(len(rec))
    peak = np.max(np.abs(rec))
    return rec / peak if peak > 0 else rec


def test_trend_detection() -> None:
    print("=== Trend detection test — patient 001 ===\n")
    sr = 22050
    pid = "001"

    # Clear old history so we get a clean run
    hist_path = _DIR / "history" / f"patient_{pid}_history.json"
    if hist_path.exists():
        hist_path.write_text("[]")

    scenarios = [
        (_cough_healthy,   "Follow-up 1: Healthy (no decline)"),
        (_cough_moderate,  "Follow-up 2: Moderate decline"),
        (_cough_severe_pd, "Follow-up 3: Severe / PD-like decline"),
    ]

    for fn, label in scenarios:
        audio_path = _DIR / "audio" / "patient_001_followup.wav"
        rec = _make_recording(fn, sr=sr)
        wavfile.write(str(audio_path), sr, np.int16(rec * 32767))

        result = analyze(str(audio_path), pid)
        print(f"{label}")
        print(f"  coughs detected : {result['num_coughs']}")
        print(f"  severity        : {result['severity']:.1f}")
        print(f"  confidence      : {result['confidence']:.2f}")
        print(f"  pd_score        : {result['pd_score']}  ({result['pd_label']})")
        print(f"  trend           : {result['trend']}")
        print(f"  flags           : {result['flags']}\n")

    print("History:")
    if hist_path.exists():
        history = json.loads(hist_path.read_text())
        for i, h in enumerate(history, 1):
            print(
                f"  [{i}] severity={h['severity']:.1f}  "
                f"pd_score={h['pd_score']}  "
                f"pd_label={h['pd_label']}  "
                f"trend={h['trend']}"
            )


if __name__ == "__main__":
    test_trend_detection()
