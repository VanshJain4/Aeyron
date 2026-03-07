"""
Train Vultr baseline from audio in a folder (healthy voices).
Run: python train_baseline.py
      python train_baseline.py --data_dir /path/to/dataset/healthy
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import librosa

from core.config import VULTR_BASE_URL, PATIENT_ID, BASELINE_DATA_DIR, BASELINE_AUDIO_EXTENSIONS
from core.quick_test import extract_quick_features, features_to_vector
from core import client_network

SAMPLE_RATE = 16000
CHUNK_SEC = 5.0


def load_and_chunk(path: Path, sr: int = SAMPLE_RATE) -> list[np.ndarray]:
    """Load audio, resample to sr, mono; return list of CHUNK_SEC-long chunks."""
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    n = int(CHUNK_SEC * sr)
    chunks = []
    for start in range(0, len(y) - n, n):
        chunks.append(y[start : start + n])
    return chunks


def collect_vectors_from_folder(data_dir: Path) -> list[list[float]]:
    """All audio files in data_dir → chunks → feature vectors (order preserved)."""
    if not data_dir.is_dir():
        return []
    vectors = []
    files = sorted(
        f for f in data_dir.iterdir()
        if f.suffix.lower() in BASELINE_AUDIO_EXTENSIONS
    )
    for path in files:
        chunks = load_and_chunk(path)
        for c in chunks:
            feats = extract_quick_features(c, sr=SAMPLE_RATE)
            vectors.append(features_to_vector(feats))
    return vectors


def main() -> int:
    parser = argparse.ArgumentParser(description="Train baseline on Vultr from audio folder (healthy voices).")
    parser.add_argument("--data_dir", type=str, default=None, help="Folder with .wav/.mp3 (default: core/data)")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else BASELINE_DATA_DIR
    if not data_dir.is_dir():
        print(f"Baseline data folder not found: {data_dir}")
        return 1
    vectors = collect_vectors_from_folder(data_dir)
    if len(vectors) < 5:
        print(f"Need at least 5 chunks (25 s total). Got {len(vectors)} from {data_dir}.")
        print("Add .wav / .mp3 files and run again.")
        return 1
    print(f"Collected {len(vectors)} vectors from {data_dir}.")
    # Server expects at least 10 vectors. Send all (or 10+ spread if we had capped).
    if len(vectors) < 10:
        print("Need at least 10 chunks (50 s total). Add more audio.")
        return 1
    if len(vectors) > 50:
        indices = [int(i * (len(vectors) - 1) / 49) for i in range(50)]
        vectors = [vectors[i] for i in indices]
        print("Sending 50 vectors (evenly spread) for enrollment.")
    else:
        print(f"Sending all {len(vectors)} vectors for enrollment.")
    print(f"Enrolling on Vultr ({VULTR_BASE_URL}) as patient_id={PATIENT_ID!r}...")
    out = client_network.enroll_baseline_vectors(VULTR_BASE_URL, PATIENT_ID, vectors)
    print("Done.", out.get("status", ""), "Baseline loss:", out.get("baseline_loss"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
