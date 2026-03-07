"""
Test trend detection by simulating multiple recordings over time.
"""

import numpy as np
import json
from scipy.io import wavfile

from analyse import analyze


def create_declining_cough(sr=22050, duration=0.3, strength=1.0, decline_factor=1.0):
    """Create a cough with applied decline factor."""
    t = np.linspace(0, duration, int(sr * duration))

    # Burst phase with decline
    burst_end = int(len(t) * 0.3)
    burst = np.exp(-8 * t[:burst_end]) * np.sin(2 * np.pi * 150 * t[:burst_end])

    # Tail phase
    tail_t = t[burst_end:] - t[burst_end]
    tail = np.exp(-3 * tail_t) * np.sin(2 * np.pi * 100 * tail_t)

    cough = np.concatenate([burst, tail])
    noise = np.random.normal(0, 0.1, len(cough))
    cough = cough + noise * strength

    # Apply decline (reduces amplitude and high frequencies)
    cough = cough * decline_factor * strength * 0.3
    cough = cough / (np.max(np.abs(cough)) + 1e-10)

    return cough


def create_follow_up_recording(num_coughs=3, strength=0.8, decline_factor=0.9):
    """Create a follow-up recording with declining strength."""
    sr = 22050
    silence_start = np.zeros(int(sr * 0.5))
    silence_between = np.zeros(int(sr * 0.3))

    recording = silence_start.copy()

    for i in range(num_coughs):
        cough = create_declining_cough(
            sr=sr,
            duration=0.3,
            strength=strength,
            decline_factor=decline_factor,
        )
        recording = np.concatenate([recording, cough, silence_between])

    background_noise = np.random.normal(0, 0.02, len(recording))
    recording = recording + background_noise
    recording = recording / np.max(np.abs(recording))

    return recording


def test_trend_detection():
    """Test trend detection with multiple follow-up recordings."""
    print("Testing trend detection with multiple recordings...\n")

    # Patient 001: simulate progressive decline
    patient_id = "001"
    sr = 22050

    decline_scenarios = [
        (0.95, "Follow-up 1: Slight decline"),
        (0.85, "Follow-up 2: Moderate decline"),
        (0.70, "Follow-up 3: Significant decline"),
    ]

    for decline_factor, label in decline_scenarios:
        print(f"Creating {label} (decline_factor={decline_factor})...")

        # Create recording
        audio = create_follow_up_recording(
            num_coughs=3,
            strength=1.2,  # Same base strength as patient_001
            decline_factor=decline_factor,
        )

        # Save
        audio_path = f"audio/patient_{patient_id}_followup.wav"
        audio_int16 = np.int16(audio * 32767)
        wavfile.write(audio_path, sr, audio_int16)

        # Analyze
        result = analyze(audio_path, patient_id)

        print(f"  Severity: {result['severity']:.1f}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Trend: {result['trend']}")
        print(f"  Flags: {result['flags']}\n")

    # Print final history
    print("\nFinal severity history for patient 001:")
    with open(f"history/patient_{patient_id}_history.json") as f:
        history = json.load(f)
        for i, entry in enumerate(history):
            print(
                f"  Reading {i + 1}: severity={entry['severity']:.1f}, "
                f"trend={entry['trend']}"
            )


if __name__ == "__main__":
    test_trend_detection()
