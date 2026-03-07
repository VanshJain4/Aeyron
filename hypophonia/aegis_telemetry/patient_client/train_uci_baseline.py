"""
Train Vultr baseline from UCI Parkinson CSV (healthy or PD rows).
UCI columns: MDVP:Fo(Hz), MDVP:Fhi(Hz), MDVP:Jitter(%), MDVP:Shimmer(dB), HNR.
Run: python train_uci_baseline.py                  # healthy (status=0) -> uci
     python train_uci_baseline.py --status 1       # PD (status=1) -> uci_pd
     python train_uci_baseline.py --csv /path/to/parkinsons.data
"""
import argparse
import sys
from pathlib import Path

from core.config import VULTR_BASE_URL, UCI_PATIENT_ID, UCI_PD_PATIENT_ID
from core import client_network

UCI_COLUMNS = [
    "MDVP:Fo(Hz)",
    "MDVP:Fhi(Hz)",
    "MDVP:Jitter(%)",
    "MDVP:Shimmer(dB)",
    "HNR",
]


def load_vectors_by_status(csv_path: Path, status: int) -> list[list[float]]:
    """Read CSV; return list of 5-dim vectors for given status (0=healthy, 1=PD)."""
    import pandas as pd

    df = pd.read_csv(csv_path)
    if "status" not in df.columns:
        raise ValueError("CSV must have 'status' column (0=healthy, 1=PD)")
    for col in UCI_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"CSV missing column: {col}")
    subset = df[df["status"] == status][UCI_COLUMNS]
    vectors = subset.values.tolist()
    return [[float(x) for x in row] for row in vectors]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train UCI baseline on Vultr (healthy status=0 or PD status=1)."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to parkinsons.data (default: ../parkinsons.data)",
    )
    parser.add_argument(
        "--status",
        type=int,
        choices=[0, 1],
        default=0,
        help="0=healthy (uci), 1=PD (uci_pd)",
    )
    parser.add_argument(
        "--patient_id",
        type=str,
        default=None,
        help="Override patient_id (default: uci for status=0, uci_pd for status=1)",
    )
    args = parser.parse_args()
    if args.csv:
        csv_path = Path(args.csv).resolve()
    else:
        csv_path = Path(__file__).resolve().parent.parent / "parkinsons.data"
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        return 1
    vectors = load_vectors_by_status(csv_path, args.status)
    if len(vectors) < 10:
        label = "healthy" if args.status == 0 else "PD"
        print(f"Need at least 10 {label} rows; got {len(vectors)}.")
        return 1
    patient_id = args.patient_id or (UCI_PD_PATIENT_ID if args.status == 1 else UCI_PATIENT_ID)
    label = "healthy" if args.status == 0 else "PD"
    print(f"Loaded {len(vectors)} {label} vectors from {csv_path}.")
    print(f"Enrolling on Vultr ({VULTR_BASE_URL}) as patient_id={patient_id!r}...")
    out = client_network.enroll_baseline_vectors(VULTR_BASE_URL, patient_id, vectors)
    print("Done.", out.get("status", ""), "Baseline loss:", out.get("baseline_loss"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
