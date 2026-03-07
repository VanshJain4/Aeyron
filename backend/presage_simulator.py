"""
Presage-shaped vitals simulator for AEYRON Sentinel demo.
POSTs vitals + breathing_rate + face/emotion every 2 seconds.
Use PRESAGE_API_KEY from environment when integrating real Presage SDK.
"""
import argparse
import random
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"

# Patient scenarios: (heart_rate, hrv, stress_score, breathing_rate, emotion_base)
# Emotion: expression list and base confidence (variance applied)
SCENARIOS = {
    "A": (72.0, 45.0, 0.2, 14.0, ["neutral", "calm"], 0.75),
    "B": (88.0, 28.0, 0.55, 18.0, ["neutral", "concerned"], 0.5),
    "C": (104.0, 14.0, 0.82, 24.0, ["anxious", "distressed", "neutral"], 0.35),
}

VARIANCE = {"hr": 2.0, "hrv": 3.0, "stress": 0.04, "breathing": 1.5, "emotion_conf": 0.08}


def _add_variance(base: float, key: str) -> float:
    delta = VARIANCE.get(key, 0.05) * (2 * random.random() - 1)
    return max(0.0, base + delta)


def run_simulator(patient: str, interval_sec: float = 2.0) -> None:
    if patient not in SCENARIOS:
        print(f"Unknown patient: {patient}. Use A, B, or C.", file=sys.stderr)
        sys.exit(1)
    hr_base, hrv_base, stress_base, br_base, expressions, conf_base = SCENARIOS[patient]
    url = f"{BASE_URL}/vitals"
    print(f"Simulating patient {patient} → POST {url} every {interval_sec}s (Ctrl+C to stop)")
    while True:
        heart_rate = _add_variance(hr_base, "hr")
        hrv = _add_variance(hrv_base, "hrv")
        stress_score = min(1.0, _add_variance(stress_base, "stress"))
        breathing_rate = _add_variance(br_base, "breathing")
        emotion_conf = min(1.0, _add_variance(conf_base, "emotion_conf"))
        expression = random.choice(expressions)
        payload = {
            "heart_rate": round(heart_rate, 1),
            "hrv": round(hrv, 1),
            "stress_score": round(stress_score, 3),
            "patient": patient,
            "breathing_rate": round(breathing_rate, 1),
            "source": "simulator",
            "face": {
                "expression": expression,
                "confidence": round(emotion_conf, 3),
                "blinking": random.random() < 0.15,
                "talking": random.random() < 0.1,
            },
        }
        try:
            r = httpx.post(url, json=payload, timeout=5.0)
            r.raise_for_status()
            print(
                f"POST ok — hr={payload['heart_rate']} br={payload['breathing_rate']} "
                f"face={expression} conf={payload['face']['confidence']}"
            )
        except httpx.ConnectError:
            print(
                "POST failed: connection refused. Is the API running? "
                "Start it with: python3 -m uvicorn main:app --port 8000",
                file=sys.stderr,
            )
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
