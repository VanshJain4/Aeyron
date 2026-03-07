"""
Step 3: Feature extraction
Extracts six features from detected cough segments.
"""

import numpy as np
import librosa


def peak_to_decay_ratio(segment):
    """
    Peak-to-decay energy ratio.
    Ratio of energy in first half (before peak) to second half (after peak).
    Higher = stronger cough with sharp burst and quick decay.
    """
    abs_seg = np.abs(segment)
    peak_idx = np.argmax(abs_seg)

    first_half = segment[:peak_idx + 1]
    second_half = segment[peak_idx + 1:]

    if len(first_half) == 0 or len(second_half) == 0:
        return 1.0

    rms_first = np.sqrt(np.mean(first_half ** 2))
    rms_second = np.sqrt(np.mean(second_half ** 2))

    if rms_second == 0:
        return 100.0

    return float(rms_first / rms_second)


def spectral_centroid_feature(segment, sr=22050):
    """
    Spectral centroid (frequency-weighted center of spectrum).
    Higher = more high-frequency energy = stronger, more turbulent cough.
    """
    centroid = librosa.feature.spectral_centroid(y=segment, sr=sr)
    return float(np.mean(centroid))


def spectral_slope(segment, sr=22050):
    """
    Spectral slope from log-magnitude spectrum.
    More negative slope = energy drops off faster at high frequencies = weakness.
    """
    # Compute FFT
    fft = np.fft.rfft(segment)
    magnitude = np.abs(fft)
    log_magnitude = np.log(magnitude + 1e-10)  # Avoid log(0)

    # Fit linear regression to get slope
    freqs = np.arange(len(log_magnitude))
    coeffs = np.polyfit(freqs, log_magnitude, 1)
    return float(coeffs[0])  # slope


def rise_time(segment, sr=22050):
    """
    Rise time: time from segment start to peak amplitude in milliseconds.
    Longer rise time = slower explosive force = weakness.
    """
    peak_idx = np.argmax(np.abs(segment))
    rise_time_ms = (peak_idx / sr) * 1000
    return float(rise_time_ms)


def zero_crossing_rate(segment):
    """
    Zero-crossing rate (mean).
    Higher ZCR = more turbulence in airflow = stronger cough.
    """
    zcr = librosa.feature.zero_crossing_rate(segment)
    return float(np.mean(zcr))


def expulsive_duration(segment, sr=22050):
    """
    Expulsive duration: portion of segment above 50% of peak amplitude in milliseconds.
    Longer duration = stronger, more sustained expulsion.
    """
    peak_amp = np.max(np.abs(segment))
    above_50_percent = np.sum(np.abs(segment) > 0.5 * peak_amp)
    duration_ms = (above_50_percent / sr) * 1000
    return float(duration_ms)


def extract_features(y, cough_segments, sr=22050):
    """
    Extract features for all detected coughs.

    Args:
        y: Audio signal
        cough_segments: List of (start_sample, end_sample) tuples
        sr: Sample rate

    Returns:
        Dict with averaged features and per-cough details
    """
    if not cough_segments:
        return None

    features_list = []

    for start, end in cough_segments:
        segment = y[start:end]

        features = {
            "peak_to_decay_ratio": peak_to_decay_ratio(segment),
            "spectral_centroid": spectral_centroid_feature(segment, sr),
            "spectral_slope": spectral_slope(segment, sr),
            "rise_time": rise_time(segment, sr),
            "zero_crossing_rate": zero_crossing_rate(segment),
            "expulsive_duration": expulsive_duration(segment, sr),
        }
        features_list.append(features)

    # Average features across all coughs
    averaged_features = {}
    for key in features_list[0].keys():
        values = [f[key] for f in features_list]
        averaged_features[key] = float(np.mean(values))
        averaged_features[f"{key}_std"] = float(np.std(values))

    return {
        "averaged": averaged_features,
        "per_cough": features_list,
    }
