"""
Presage-shaped vitals simulator for AEYRON Sentinel demo.
POSTs realistic vitals to the backend every 2 seconds.
Use PRESAGE_API_KEY from environment when integrating real Presage SDK.
"""
import argparse
import os
import random
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"

# Patient scenarios: (heart_rate, hrv, stress_score) base values
SCENARIOS = {
    "A": (72.0, 45.0, 0.2),   # healthy, stable
    "B": (88.0, 28.0, 0.55),  # warning, drifting
    "C": (104.0, 14.0, 0.82), # critical, climbing
}

VARIANCE = {"hr": 2.0, "hrv": 3.0, "stress": 0.04}


def _add_variance(base: float, key: str) -> float:
    delta = VARIANCE[key] * (2 * random.random() - 1)
    return max(0.0, base + delta)


def run_simulator(patient: str, interval_sec: float = 2.0) -> None:
    if patient not in SCENARIOS:
        print(f"Unknown patient: {patient}. Use A, B, or C.", file=sys.stderr)
        sys.exit(1)
    hr_base, hrv_base, stress_base = SCENARIOS[patient]
    url = f"{BASE_URL}/vitals"
    print(f"Simulating patient {patient} → POST {url} every {interval_sec}s (Ctrl+C to stop)")
    while True:
        heart_rate = _add_variance(hr_base, "hr")
        hrv = _add_variance(hrv_base, "hrv")
        stress_score = min(1.0, _add_variance(stress_base, "stress"))
        payload = {
            "heart_rate": round(heart_rate, 1),
            "hrv": round(hrv, 1),
            "stress_score": round(stress_score, 3),
            "patient": patient,
        }
        try:
            r = httpx.post(url, json=payload, timeout=5.0)
            r.raise_for_status()
            print(f"POST ok — hr={payload['heart_rate']} hrv={payload['hrv']} stress={payload['stress_score']}")
        except httpx.HTTPError as e:
            print(f"POST failed: {e}", file=sys.stderr)
        time.sleep(interval_sec)


def main() -> None:
    ap = argparse.ArgumentParser(description="Presage vitals simulator for Sentinel demo")
    ap.add_argument(
        "patient",
        choices=["A", "B", "C"],
        help="Patient scenario: A=healthy, B=warning, C=critical",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between POSTs (default: 2)",
    )
    args = ap.parse_args()
    run_simulator(args.patient, args.interval)


if __name__ == "__main__":
    main()
