"""
Demo: compare healthy vs PD audio file directly (no mic needed).
Extracts Praat features from each file, sends to Vultr, prints results.

Usage:
    python3 demo_compare.py --healthy <wav> --pd <wav>
    python3 demo_compare.py --pd <wav>          # just score one file
"""
import argparse
import sys
from pathlib import Path

import librosa
import numpy as np

from core.config import VULTR_BASE_URL, PATIENT_ID, UCI_PATIENT_ID, UCI_PD_PATIENT_ID
from core.acoustic_features import extract_features, uci_features_to_vector, UCI_FEATURE_ORDER
from core.quick_test import extract_quick_features, features_to_vector, FEATURE_ORDER
from core import client_network

SAMPLE_RATE = 16000
CHUNK_SEC = 5.0


def analyze_file(path: str, label: str) -> None:
    y, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    n = int(CHUNK_SEC * SAMPLE_RATE)

    # Personal baseline (librosa, first 10s)
    chunk1 = y[:n]
    chunk2 = y[n:2*n] if len(y) >= 2*n else y[:n]
    v1 = features_to_vector(extract_quick_features(chunk1, sr=SAMPLE_RATE))
    v2 = features_to_vector(extract_quick_features(chunk2, sr=SAMPLE_RATE))
    personal_vec = list(np.mean([v1, v2], axis=0))
    out_p = client_network.infer(VULTR_BASE_URL, PATIENT_ID, personal_vec)

    # UCI comparison (Praat, first 5s = task_a, next 5s = task_b)
    task_a = y[:n]
    task_b = y[n:2*n] if len(y) >= 2*n else y[:n]
    feats = extract_features(task_a, task_b)
    uci_vec = uci_features_to_vector(feats)
    out_h = client_network.infer(VULTR_BASE_URL, UCI_PATIENT_ID, uci_vec)
    out_pd = client_network.infer(VULTR_BASE_URL, UCI_PD_PATIENT_ID, uci_vec)

    import math
    mse_h = out_h.get("anomaly_score", 0)
    mse_pd = out_pd.get("anomaly_score", 0)
    closer = "HEALTHY" if mse_h <= mse_pd else "PD"
    if mse_h > 0 and mse_pd > 0:
        k = 3.0
        log_ratio = k * math.log(mse_pd / mse_h)
        p_healthy = 100.0 / (1.0 + math.exp(-log_ratio))
    else:
        p_healthy = 100.0 * mse_pd / (mse_h + mse_pd) if (mse_h + mse_pd) > 0 else 50.0
    p_pd = 100.0 - p_healthy

    mse_p = out_p.get("anomaly_score", 0)
    th_p = out_p.get("threshold", 1)
    personal_status = out_p.get("status", "?")

    print(f"\n{'═'*56}")
    print(f"  {label}")
    print(f"  File: {Path(path).name}")
    print(f"{'═'*56}")
    print(f"\n  UCI features (Praat):")
    for name, val in zip(UCI_FEATURE_ORDER, uci_vec):
        print(f"    {name:12s} : {val:.5f}")
    print(f"\n  UCI result:")
    print(f"    MSE vs healthy  : {mse_h:.6f}")
    print(f"    MSE vs PD       : {mse_pd:.6f}")
    print(f"    ▶  Closer to    : {closer}  ({p_healthy:.1f}% healthy / {p_pd:.1f}% PD)")
    print(f"\n  Personal baseline:")
    print(f"    MSE             : {mse_p:.6f}  (threshold: {th_p:.6f})")
    print(f"    ▶  Status       : {personal_status.upper()}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthy", type=str, default=None)
    parser.add_argument("--pd", type=str, required=True)
    args = parser.parse_args()

    if args.healthy:
        analyze_file(args.healthy, "HEALTHY VOICE")
    analyze_file(args.pd, "PD VOICE")
    print(f"\n{'═'*56}\n")


if __name__ == "__main__":
    main()
