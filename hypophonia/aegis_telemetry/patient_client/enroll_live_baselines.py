"""
Enroll UCI healthy and PD baselines from actual audio files using the
same Praat feature pipeline as the live demo.

This fixes the clinical-vs-live-mic mismatch: training and inference
now use identical feature extraction on the same type of audio.

Usage:
    python3 enroll_live_baselines.py --pd_dir /path/to/PD/wavs
    python3 enroll_live_baselines.py --pd_dir /path/to/PD/wavs --healthy_dir /path/to/healthy/wavs
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import librosa

from core.config import VULTR_BASE_URL, UCI_PATIENT_ID, UCI_PD_PATIENT_ID, BASELINE_DATA_DIR
from core.acoustic_features import extract_features, uci_features_to_vector
from core import client_network

SAMPLE_RATE = 16000
CHUNK_SEC = 5.0
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".m4a")


def extract_uci_vectors_from_dir(audio_dir: Path, max_files: int = 200) -> list[list[float]]:
    """
    Load audio files, extract [Jitter, Shimmer, HNR, NHR, DDP] from each.
    Uses first CHUNK_SEC as task_a (vowel/quality features).
    Skips clips where all features are zero (unvoiced / too short).
    """
    files = sorted(f for f in audio_dir.rglob("*") if f.suffix.lower() in AUDIO_EXTS)
    if not files:
        print(f"  No audio files found in {audio_dir}")
        return []

    vectors = []
    skipped = 0
    n = int(CHUNK_SEC * SAMPLE_RATE)
    for path in files[:max_files]:
        try:
            y, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
            if len(y) < int(1.0 * SAMPLE_RATE):
                skipped += 1
                continue
            # Extract one vector per 5s chunk (same as train_baseline.py)
            chunk_starts = range(0, len(y) - n, n)
            if not chunk_starts:
                chunk_starts = [0]
            for start in chunk_starts:
                task_a = y[start:start + n]
                task_b = y[start + n:start + 2*n] if len(y) >= start + 2*n else task_a
                feats = extract_features(task_a, task_b)
                vec = uci_features_to_vector(feats)
                if all(v == 0.0 for v in vec):
                    skipped += 1
                    continue
                vectors.append(vec)
        except Exception:
            skipped += 1
            continue

    print(f"  Extracted {len(vectors)} vectors ({skipped} skipped) from {audio_dir}")
    return vectors


def enroll(patient_id: str, vectors: list[list[float]], label: str) -> None:
    if len(vectors) < 10:
        print(f"  Need at least 10 vectors for {label}, got {len(vectors)}. Aborting.")
        sys.exit(1)
    # Cap at 200 evenly spread to avoid overwhelming the server
    if len(vectors) > 200:
        idx = [int(i * (len(vectors) - 1) / 199) for i in range(200)]
        vectors = [vectors[i] for i in idx]
        print(f"  Sending 200 vectors (evenly spread) for {label}")
    else:
        print(f"  Sending {len(vectors)} vectors for {label}")
    out = client_network.enroll_baseline_vectors(VULTR_BASE_URL, patient_id, vectors)
    print(f"  Done. {out.get('status', '')} Baseline loss: {out.get('baseline_loss')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enroll UCI baselines from real audio files.")
    parser.add_argument("--pd_dir", type=str, required=True,
                        help="Directory of PD patient audio (searched recursively)")
    parser.add_argument("--healthy_dir", type=str, default=None,
                        help="Directory of healthy audio (default: core/data/)")
    parser.add_argument("--max_files", type=int, default=200,
                        help="Max audio files to process per class (default: 200)")
    args = parser.parse_args()

    pd_dir = Path(args.pd_dir).resolve()
    healthy_dir = Path(args.healthy_dir).resolve() if args.healthy_dir else BASELINE_DATA_DIR

    print(f"\n=== PD baseline → patient_id='{UCI_PD_PATIENT_ID}' ===")
    print(f"  Source: {pd_dir}")
    pd_vecs = extract_uci_vectors_from_dir(pd_dir, max_files=args.max_files)
    enroll(UCI_PD_PATIENT_ID, pd_vecs, "PD")

    print(f"\n=== Healthy baseline → patient_id='{UCI_PATIENT_ID}' ===")
    print(f"  Source: {healthy_dir}")
    healthy_vecs = extract_uci_vectors_from_dir(healthy_dir, max_files=args.max_files)
    enroll(UCI_PATIENT_ID, healthy_vecs, "healthy")

    print("\nDone. Both baselines enrolled from real audio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
