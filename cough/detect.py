"""
Step 2: Cough detection
Detects cough segments in raw audio using amplitude envelope and dynamic thresholding.
"""

import numpy as np
import librosa
from scipy import signal


def detect_coughs(audio_path, sr=22050):
    y, _ = librosa.load(audio_path, sr=sr)

    # Compute amplitude envelope using rolling RMS
    frame_length = int(sr * 0.01)  # 10ms frames
    hop_length = frame_length // 2

    # Compute RMS for each frame
    frames = np.array_split(y, len(y) // frame_length)
    rms = np.array([np.sqrt(np.mean(frame ** 2)) for frame in frames])

    # Smooth envelope with a median filter for stability
    envelope = signal.medfilt(rms, kernel_size=5)

    # Dynamic threshold: 3x the median amplitude
    threshold = 3 * np.median(envelope)

    # Upsample envelope back to original sample rate for alignment
    envelope_full = np.repeat(envelope, hop_length)
    envelope_full = envelope_full[:len(y)]

    # Find regions above threshold
    above_threshold = envelope_full > threshold

    # Find contiguous regions
    changes = np.diff(above_threshold.astype(int))
    starts = np.where(changes == 1)[0] + 1
    ends = np.where(changes == -1)[0]

    # Handle edge cases
    if above_threshold[0]:
        starts = np.concatenate([[0], starts])
    if above_threshold[-1]:
        ends = np.concatenate([ends, [len(y)]])

    # Filter by duration: keep only 100ms to 800ms
    min_duration_samples = int(sr * 0.1)  # 100ms
    max_duration_samples = int(sr * 0.8)  # 800ms

    coughs = []
    for start, end in zip(starts, ends):
        duration = end - start
        if min_duration_samples <= duration <= max_duration_samples:
            coughs.append((start, end))

    return coughs
