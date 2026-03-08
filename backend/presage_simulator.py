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

# Patient scenarios:
#   heart_rate, hrv, stress_score, breathing_rate, expressions, emotion_conf_base,
#   voice_pd_prob, voice_svm_conf, cough_pd_score, cough_count
SCENARIOS = {
    "A": {
        "hr": 72.0, "hrv": 45.0, "stress": 0.2, "br": 14.0,
        "expressions": ["neutral", "calm"], "conf": 0.75,
        "voice_pd": 0.15, "voice_conf": 0.92, "cough_pd": 0.12, "cough_n": 2,
    },
    "B": {
        "hr": 88.0, "hrv": 28.0, "stress": 0.55, "br": 18.0,
        "expressions": ["neutral", "concerned"], "conf": 0.5,
        "voice_pd": 0.48, "voice_conf": 0.78, "cough_pd": 0.42, "cough_n": 5,
    },
    "C": {
        "hr": 104.0, "hrv": 14.0, "stress": 0.82, "br": 24.0,
        "expressions": ["anxious", "distressed", "neutral"], "conf": 0.35,
        "voice_pd": 0.82, "voice_conf": 0.91, "cough_pd": 0.71, "cough_n": 8,
    },
}

VARIANCE = {
    "hr": 2.0, "hrv": 3.0, "stress": 0.04, "breathing": 1.5, "emotion_conf": 0.08,
    "voice_pd": 0.06, "voice_conf": 0.04, "cough_pd": 0.05, "cough_n": 2,
}


def _add_variance(base: float, key: str) -> float:
    delta = VARIANCE.get(key, 0.05) * (2 * random.random() - 1)
    return max(0.0, base + delta)


def run_simulator(patient: str, interval_sec: float = 2.0) -> None:
    if patient not in SCENARIOS:
        print(f"Unknown patient: {patient}. Use A, B, or C.", file=sys.stderr)
        sys.exit(1)
    s = SCENARIOS[patient]
    print(f"Simulating patient {patient} → all modalities every {interval_sec}s (Ctrl+C to stop)")
    tick = 0
    while True:
        heart_rate = _add_variance(s["hr"], "hr")
        hrv = _add_variance(s["hrv"], "hrv")
        stress_score = min(1.0, _add_variance(s["stress"], "stress"))
        breathing_rate = _add_variance(s["br"], "breathing")
        emotion_conf = min(1.0, _add_variance(s["conf"], "emotion_conf"))
        expression = random.choice(s["expressions"])

        # --- Vitals + Face ---
        vitals_payload = {
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

        # --- Voice (every tick) ---
        voice_pd = min(1.0, max(0.0, _add_variance(s["voice_pd"], "voice_pd")))
        voice_conf = min(1.0, max(0.0, _add_variance(s["voice_conf"], "voice_conf")))
        voice_payload = {
            "pd_probability": round(voice_pd, 4),
            "svm_confidence": round(voice_conf, 4),
            "features": {
                "spectral_flatness": round(0.1 + random.random() * 0.4, 4),
                "hnr": round(10 + random.random() * 15, 2),
                "jitter": round(0.002 + random.random() * 0.01, 5),
            },
            "source": "simulator",
        }

        # --- Cough (every 3rd tick) ---
        cough_payload = None
        if tick % 3 == 0:
            cough_pd = min(1.0, max(0.0, _add_variance(s["cough_pd"], "cough_pd")))
            cough_n = max(1, int(s["cough_n"] + (random.random() - 0.5) * VARIANCE["cough_n"] * 2))
            cough_label = "HIGH_RISK" if cough_pd >= 0.6 else "MODERATE_RISK" if cough_pd >= 0.35 else "LOW_RISK"
            cough_payload = {
                "pd_score": round(cough_pd, 4),
                "pd_label": cough_label,
                "num_coughs": cough_n,
                "features": {
                    "crest_factor": round(5 + random.random() * 8, 2),
                    "spectral_centroid": round(1500 + random.random() * 1500, 0),
                    "rise_time": round(0.01 + random.random() * 0.05, 4),
                },
            }

        try:
            httpx.post(f"{BASE_URL}/vitals", json=vitals_payload, timeout=5.0)
            httpx.post(f"{BASE_URL}/voice", json=voice_payload, timeout=5.0)
            if cough_payload:
                httpx.post(f"{BASE_URL}/cough", json=cough_payload, timeout=5.0)
            parts = [
                f"hr={vitals_payload['heart_rate']}",
                f"voice={voice_payload['pd_probability']:.0%}",
            ]
            if cough_payload:
                parts.append(f"cough={cough_payload['pd_score']:.0%}({cough_payload['num_coughs']})")
            parts.append(f"face={expression}")
            print(f"[{patient}] " + " | ".join(parts))
        except httpx.ConnectError:
            print("Connection refused. Is the API running?", file=sys.stderr)
        except httpx.HTTPError as e:
            print(f"POST failed: {e}", file=sys.stderr)

        tick += 1
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
