"""
Quick live cough test — record from mic, run full pipeline, print results.

Usage:
    python live_test.py [seconds] [patient_id]

Defaults: 8 seconds, patient_id = "live"
"""
from __future__ import annotations

import sys
import json
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

from detect import detect_coughs
from features import extract_features
from pd_classifier import pd_likelihood

SR = 22050


def record(duration: float) -> np.ndarray:
    print(f"\nRecording {duration:.0f} s — cough now...")
    audio = sd.rec(int(duration * SR), samplerate=SR, channels=1, dtype="float32")
    sd.wait()
    print("Done recording.\n")
    return audio.squeeze()


def run(duration: float = 8.0, patient_id: str = "live") -> None:
    y = record(duration)

    # Save to temp WAV so detect_coughs can load it
    tmp = Path(tempfile.mktemp(suffix=".wav"))
    wavfile.write(str(tmp), SR, np.int16(y * 32767))

    try:
        segments = detect_coughs(str(tmp), sr=SR)
    finally:
        tmp.unlink(missing_ok=True)

    print(f"Coughs detected : {len(segments)}")

    if not segments:
        print("No coughs found. Try coughing louder or closer to the mic.")
        return

    for i, (s, e) in enumerate(segments, 1):
        print(f"  Cough {i}: {s/SR*1000:.0f} ms – {e/SR*1000:.0f} ms  ({(e-s)/SR*1000:.0f} ms long)")

    feats = extract_features(y, segments, sr=SR)
    avg = feats["averaged"]

    pd_score, pd_label = pd_likelihood(avg)

    print("\n── Features ──────────────────────────────────")
    print(f"  Spectral centroid   : {avg['spectral_centroid']:.1f} Hz")
    print(f"  Zero-crossing rate  : {avg['zero_crossing_rate']:.4f}")
    print(f"  Crest factor        : {avg['crest_factor']:.2f}")
    print(f"  Phase power ratio   : {avg['phase_power_ratio']:.4f}")
    print(f"  Rise time           : {avg['rise_time']:.1f} ms")
    print(f"  Peak-to-decay ratio : {avg['peak_to_decay_ratio']:.4f}")
    print(f"  Expulsive duration  : {avg['expulsive_duration']:.1f} ms")

    print("\n── PD Assessment ─────────────────────────────")
    print(f"  PD score  : {pd_score:.4f}")
    print(f"  PD label  : {pd_label}")
    print()

    bar_len = 40
    filled = int(pd_score * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"  [{bar}] {pd_score*100:.1f}%")
    print()

    if pd_label == "LOW_RISK":
        print("  → Cough characteristics consistent with healthy/normal.")
    elif pd_label == "MODERATE_RISK":
        print("  → Some PD-associated cough characteristics detected.")
    else:
        print("  → Cough characteristics strongly associated with PD.")

    print("\n  (Not a clinical diagnosis.)")


if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    pid = sys.argv[2] if len(sys.argv) > 2 else "live"
    run(duration, pid)
