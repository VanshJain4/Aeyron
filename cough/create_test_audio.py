"""
Create synthetic test audio for three patient scenarios.
"""

import numpy as np
import json
import os
from scipy.io import wavfile


def create_cough(sr=22050, duration=0.3, strength=1.0):
    """
    Create synthetic cough audio.

    Args:
        sr: Sample rate
        duration: Cough duration in seconds
        strength: Amplitude multiplier (1.0 = normal, 0.5 = weak, 1.5 = strong)
    """
    t = np.linspace(0, duration, int(sr * duration))

    # Burst phase (first 30% of cough): sharp attack, decaying
    burst_end = int(len(t) * 0.3)
    burst = np.exp(-8 * t[:burst_end]) * np.sin(2 * np.pi * 150 * t[:burst_end])

    # Tail phase (rest): lower frequency, gradual decay
    tail_t = t[burst_end:] - t[burst_end]
    tail = np.exp(-3 * tail_t) * np.sin(2 * np.pi * 100 * tail_t)

    cough = np.concatenate([burst, tail])

    # Add some turbulence (high-frequency noise)
    noise = np.random.normal(0, 0.1, len(cough))
    cough = cough + noise * strength

    # Apply strength and normalize
    cough = cough * strength * 0.3
    cough = cough / np.max(np.abs(cough))

    return cough


def create_recording(patient_type, sr=22050, num_coughs=3):
    """
    Create a recording with multiple coughs and background silence.

    Args:
        patient_type: "healthy", "moderate", or "severe"
        sr: Sample rate
        num_coughs: Number of coughs in the recording
    """
    # Set strength based on patient type
    strength_map = {
        "healthy": 1.2,      # Strong coughs
        "moderate": 0.8,     # Medium coughs
        "severe": 0.4,       # Weak coughs
    }
    strength = strength_map.get(patient_type, 1.0)

    # Create silence padding (0.5s at start, 0.3s between coughs)
    silence_start = np.zeros(int(sr * 0.5))
    silence_between = np.zeros(int(sr * 0.3))

    recording = silence_start.copy()

    for i in range(num_coughs):
        cough = create_cough(sr=sr, duration=0.3, strength=strength)
        recording = np.concatenate([recording, cough, silence_between])

    # Add background noise (very low level)
    background_noise = np.random.normal(0, 0.02, len(recording))
    recording = recording + background_noise

    # Normalize to [-1, 1]
    recording = recording / np.max(np.abs(recording))

    return recording


def main():
    """Create test audio files for three patient scenarios."""
    sr = 22050

    # Create audio directory if needed
    os.makedirs("audio", exist_ok=True)

    patients = {
        "001": "healthy",
        "002": "moderate",
        "003": "severe",
    }

    for patient_id, patient_type in patients.items():
        print(f"Creating test audio for patient {patient_id} ({patient_type})...")

        # Create recording at 22050 Hz
        audio = create_recording(patient_type, sr=sr, num_coughs=3)
        audio_int16 = np.int16(audio * 32767)

        # Save as WAV file at 22050 Hz
        wav_path = f"audio/patient_{patient_id}.wav"
        wavfile.write(wav_path, sr, audio_int16)
        print(f"  → Saved to {wav_path}")

        # Save as OPUS file at 16000 Hz (OPUS only supports 8k, 12k, 16k, 24k, 48k)
        try:
            import soundfile as sf
            from scipy.signal import resample

            # Resample to 16000 Hz for OPUS
            opus_sr = 16000
            audio_opus = resample(audio, int(len(audio) * opus_sr / sr))

            opus_path = f"audio/patient_{patient_id}.opus"
            sf.write(opus_path, audio_opus, opus_sr, format='OGG', subtype='OPUS')
            print(f"  → Saved to {opus_path} (16000 Hz)")
        except ImportError:
            print(f"  ⚠️  soundfile not installed, skipping OPUS format")
        except Exception as e:
            print(f"  ⚠️  Could not save OPUS format: {e}")


if __name__ == "__main__":
    main()
