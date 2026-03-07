"""
Hypophonia voice only: 5 features — rms_mean (Task B), pitch_std (Task B), jitter (A), shimmer (A), hnr (A).
Pitch: pitch_floor=75, pitch_ceiling=500. No amplitude normalization.
"""
import numpy as np
import parselmouth
from parselmouth.praat import call

PITCH_FLOOR = 75.0
PITCH_CEILING = 500.0
SAMPLE_RATE = 16000
FEATURE_ORDER = ("rms_mean", "pitch_std", "jitter", "shimmer", "hnr")
# UCI Parkinson CSV: Fo(Hz), Fhi(Hz), Jitter(%), Shimmer(dB), HNR
UCI_FEATURE_ORDER = ("Fo", "Fhi", "Jitter", "Shimmer", "HNR")
# UCI HNR in data is 8–33 dB; Praat can return very negative on non-vowel → clamp for comparison
UCI_HNR_MIN, UCI_HNR_MAX = 8.0, 33.0


def _sound_from_samples(samples: np.ndarray, sr: float = SAMPLE_RATE) -> parselmouth.Sound:
    return parselmouth.Sound(samples, sampling_frequency=sr)


def _pitch_from_sound(sound: parselmouth.Sound):
    return sound.to_pitch(pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)


def features_from_task_b(sound: parselmouth.Sound) -> tuple[float, float, float, float]:
    """rms_mean, pitch_std, pitch_mean, pitch_max from Task B (spontaneous speech)."""
    values = sound.values[0]
    rms_mean = float(np.sqrt(np.mean(values ** 2)))
    pitch = _pitch_from_sound(sound)
    f0 = pitch.selected_array["frequency"]
    f0_voiced = f0[f0 > 0]
    if len(f0_voiced) == 0:
        return rms_mean, 0.0, 0.0, 0.0
    pitch_std = float(np.nanstd(f0_voiced))
    pitch_mean = float(np.nanmean(f0_voiced))
    pitch_max = float(np.nanmax(f0_voiced))
    return rms_mean, pitch_std, pitch_mean, pitch_max


def features_from_task_a(sound: parselmouth.Sound) -> tuple[float, float, float]:
    """jitter, shimmer, hnr from Task A (sustained vowel) via Praat. Returns (0,0,0) if unvoiced."""
    try:
        pitch = _pitch_from_sound(sound)
        # To PointProcess (cc) takes no extra args; Pitch already has floor/ceiling from to_pitch()
        point_process = call([sound, pitch], "To PointProcess (cc)")
        jitter = call(point_process, "Get jitter (local)...", 0.0, 0.0, 0.0001, 0.02, 1.3)
        shimmer = call([sound, point_process], "Get shimmer (local)...", 0.0, 0.0, 0.0001, 0.02, 1.3, 1.6)
    except Exception:
        jitter, shimmer = 0.0, 0.0
    harmonicity = sound.to_harmonicity(time_step=0.01, minimum_pitch=PITCH_FLOOR)
    times = harmonicity.xs()
    hnr_values = [harmonicity.get_value(t) for t in times if not np.isnan(harmonicity.get_value(t))]
    hnr = float(np.mean(hnr_values)) if hnr_values else 0.0
    return jitter, shimmer, hnr


def extract_features(
    task_a_samples: np.ndarray,
    task_b_samples: np.ndarray,
) -> dict[str, float]:
    """
    Voice-only: rms_mean, pitch_std, pitch_mean, pitch_max, jitter, shimmer, hnr.
    """
    sound_a = _sound_from_samples(task_a_samples)
    sound_b = _sound_from_samples(task_b_samples)
    rms_mean, pitch_std, pitch_mean, pitch_max = features_from_task_b(sound_b)
    jitter, shimmer, hnr = features_from_task_a(sound_a)
    return {
        "rms_mean": rms_mean,
        "pitch_std": pitch_std,
        "pitch_mean": pitch_mean,
        "pitch_max": pitch_max,
        "jitter": jitter,
        "shimmer": shimmer,
        "hnr": hnr,
    }


def features_to_vector(features: dict[str, float]) -> list[float]:
    """Deterministic 1D vector of length 5 for network transmission."""
    return [features[k] for k in FEATURE_ORDER]


def uci_features_to_vector(features: dict[str, float]) -> list[float]:
    """5-dim vector for UCI comparison. HNR clamped to UCI range so healthy/PD MSE is meaningful."""
    hnr = float(features["hnr"])
    hnr_clamped = max(UCI_HNR_MIN, min(UCI_HNR_MAX, hnr))
    return [
        features["pitch_mean"],
        features["pitch_max"],
        features["jitter"],
        features["shimmer"],
        hnr_clamped,
    ]
