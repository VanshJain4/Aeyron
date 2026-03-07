"""
Demo: Analyze cough audio in both WAV and OPUS formats
Shows that the system supports multiple audio formats transparently.
"""

import json
from analyse import analyze


def main():
    print("=" * 60)
    print("COUGH WEAKNESS DETECTION - FORMAT SUPPORT DEMO")
    print("=" * 60)
    print()

    patients = ["001", "002", "003"]
    formats = [".wav", ".opus"]

    for patient_id in patients:
        print(f"\nPatient {patient_id}:")
        print("-" * 40)

        for fmt in formats:
            audio_path = f"audio/patient_{patient_id}{fmt}"
            result = analyze(audio_path, patient_id)

            print(f"  {fmt.upper():5} → ", end="")
            print(f"Severity: {result['severity']:5.1f}, ", end="")
            print(f"Confidence: {result['confidence']:.2f}, ", end="")
            print(f"Status: {result['status']}")

    print()
    print("=" * 60)
    print("✓ Both WAV and OPUS formats work seamlessly!")
    print("=" * 60)


if __name__ == "__main__":
    main()
