"""
Hypophonia voice only: 5 features — rms_mean (Task B), pitch_std (Task B), jitter (A), shimmer (A), hnr (A).
Pitch: pitch_floor=75, pitch_ceiling=500. No amplitude normalization.

UCI comparison features (5-dim, robust to phone-speaker→mic audio):
  hnr            — Praat harmonicity 75th pct (healthy > PD)
  spectral_flatness — librosa mean flatness (PD noisier → higher)
  mfcc2          — 2nd MFCC mean (spectral tilt, gender-neutral)
  voiced_fraction — fraction voiced frames (PD less voiced)
  energy_cv      — RMS energy coeff of variation (tremor → higher in PD)
"""
import numpy as np
import librosa
import parselmouth
from parselmouth.praat import call

PITCH_FLOOR = 75.0
PITCH_CEILING = 500.0
SAMPLE_RATE = 16000
FEATURE_ORDER = ("rms_mean", "pitch_std", "jitter", "shimmer", "hnr")
# UCI features: robust 5-dim set that works on phone-played audio.
# Jitter/Shimmer removed — Praat PointProcess frequently returns 0 on
# compressed or room-acoustics audio, making the feature useless.
UCI_FEATURE_ORDER = ("HNR", "SpectralFlatness", "MFCC2", "VoicedFraction", "EnergyCv")


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
    # Only include voiced frames (Praat returns NaN for unvoiced).
    # Exclude extreme negatives (< -60 dB) which are silence/background.
    # Use 75th percentile rather than mean: this captures the clearest voiced
    # frames, which is comparable to UCI clinical recordings where subjects
    # sustained a clean vowel. Mean HNR is dragged down by room noise on
    # live mic; 75th percentile stays discriminative between healthy and PD.
    hnr_values = [
        v for t in times
        for v in [harmonicity.get_value(t)]
        if not np.isnan(v) and v > -60.0
    ]
    hnr = float(np.percentile(hnr_values, 75)) if hnr_values else 0.0
    return jitter, shimmer, hnr


def _librosa_features(samples: np.ndarray, sr: float = SAMPLE_RATE) -> dict[str, float]:
    """Compute librosa-based features that are robust on any audio."""
    hop = 512
    # Spectral flatness: mean across frames (PD voices have higher flatness = noisier)
    flatness = librosa.feature.spectral_flatness(y=samples, hop_length=hop)
    spectral_flatness = float(np.mean(flatness))

    # MFCC2: 2nd mel-frequency cepstral coefficient mean (spectral tilt, ~gender-neutral)
    mfccs = librosa.feature.mfcc(y=samples, sr=sr, n_mfcc=3, hop_length=hop)
    mfcc2 = float(np.mean(mfccs[1]))  # index 1 = 2nd coefficient

    # Voiced fraction: fraction of frames where pitch is detected
    f0, voiced_flag, _ = librosa.pyin(
        samples, fmin=PITCH_FLOOR, fmax=PITCH_CEILING, sr=sr, hop_length=hop
    )
    voiced_fraction = float(np.mean(voiced_flag)) if voiced_flag is not None else 0.5

    # Energy CV: coefficient of variation of RMS energy (tremor → higher in PD)
    rms = librosa.feature.rms(y=samples, hop_length=hop)[0]
    rms_nonzero = rms[rms > 1e-6]
    energy_cv = float(np.std(rms_nonzero) / np.mean(rms_nonzero)) if len(rms_nonzero) > 1 else 0.5

    return {
        "spectral_flatness": spectral_flatness,
        "mfcc2": mfcc2,
        "voiced_fraction": voiced_fraction,
        "energy_cv": energy_cv,
    }


def extract_features(
    task_a_samples: np.ndarray,
    task_b_samples: np.ndarray,
) -> dict[str, float]:
    """
    Voice-only: rms_mean, pitch_std, pitch_mean, pitch_max, jitter, shimmer, hnr,
    plus robust librosa features: spectral_flatness, mfcc2, voiced_fraction, energy_cv.
    """
    sound_a = _sound_from_samples(task_a_samples)
    sound_b = _sound_from_samples(task_b_samples)
    rms_mean, pitch_std, pitch_mean, pitch_max = features_from_task_b(sound_b)
    jitter, shimmer, hnr = features_from_task_a(sound_a)
    # Combine task_a and task_b audio for librosa features (more signal = more stable)
    combined = np.concatenate([task_a_samples, task_b_samples])
    lib_feats = _librosa_features(combined)
    return {
        "rms_mean": rms_mean,
        "pitch_std": pitch_std,
        "pitch_mean": pitch_mean,
        "pitch_max": pitch_max,
        "jitter": jitter,
        "shimmer": shimmer,
        "hnr": hnr,
        **lib_feats,
    }


def features_to_vector(features: dict[str, float]) -> list[float]:
    """Deterministic 1D vector of length 5 for network transmission."""
    return [features[k] for k in FEATURE_ORDER]


def uci_features_to_vector(features: dict[str, float]) -> list[float]:
    """
    5-dim vector: [HNR, SpectralFlatness, MFCC2, VoicedFraction, EnergyCv].
    All computed by extract_features() and work on any audio (phone-played, live mic).
    PD voices: lower HNR, higher flatness, different MFCC2, less voiced, higher energy_cv.
    """
    hnr = float(features.get("hnr", 0.0))
    spectral_flatness = float(features.get("spectral_flatness", 0.5))
    mfcc2 = float(features.get("mfcc2", 0.0))
    voiced_fraction = float(features.get("voiced_fraction", 0.5))
    energy_cv = float(features.get("energy_cv", 0.5))
    return [hnr, spectral_flatness, mfcc2, voiced_fraction, energy_cv]
