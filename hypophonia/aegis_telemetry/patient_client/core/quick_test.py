"""
Quick test (MARTA-inspired): single recording, spectrogram summary via librosa only.
No Praat, no Silero VAD. One 5s recording → 5 summary stats relevant to hypophonia.
Uses MARTA-style framing: 400ms frames, 65 mel bins, log-mel (no phoneme labels).
"""
import numpy as np
import librosa

SAMPLE_RATE = 16000
DURATION_SEC = 5.0
N_FFT = 512
N_MELS = 65
# win_length must be <= n_fft (librosa). 512 samples = 32 ms at 16 kHz.
WIN_LENGTH = N_FFT
HOP_LENGTH = N_FFT // 2  # 50% overlap


def extract_quick_features(samples: np.ndarray, sr: int = SAMPLE_RATE) -> dict[str, float]:
    """
    From one short recording: mean energy (loudness), energy std (prosody variation),
    spectral centroid mean, spectral bandwidth mean, zero-crossing mean.
    Hypophonia → low energy, low energy variance (flat/monotone).
    """
    if len(samples) < int(sr * 1.0):
        raise ValueError("Recording too short (need at least 1 s)")
    win_length = WIN_LENGTH
    hop_length = HOP_LENGTH
    mel = librosa.feature.melspectrogram(
        y=samples.astype(np.float32),
        sr=sr,
        n_fft=N_FFT,
        hop_length=hop_length,
        win_length=win_length,
        n_mels=N_MELS,
        center=False,
    )
    ref = float(np.max(mel)) + 1e-10  # avoid ref=0 (silent) → -inf/nan
    log_mel = librosa.power_to_db(mel, ref=ref)
    # Per-frame energy (mean over mel bins)
    frame_energy = np.mean(log_mel, axis=0)
    mean_energy = float(np.mean(frame_energy))
    energy_std = float(np.std(frame_energy))
    # If silent/near-silent we can get -inf/nan; clamp to finite
    if not np.isfinite(mean_energy):
        mean_energy = -80.0
    if not np.isfinite(energy_std):
        energy_std = 0.0
    # Spectral shape (over full signal)
    spectral_centroid = librosa.feature.spectral_centroid(
        y=samples.astype(np.float32), sr=sr, n_fft=N_FFT, hop_length=hop_length
    ).squeeze()
    spectral_bandwidth = librosa.feature.spectral_bandwidth(
        y=samples.astype(np.float32), sr=sr, n_fft=N_FFT, hop_length=hop_length
    ).squeeze()
    zcr = librosa.feature.zero_crossing_rate(
        samples.astype(np.float32), frame_length=win_length, hop_length=hop_length
    ).squeeze()
    sc_mean = float(np.mean(spectral_centroid))
    sb_mean = float(np.mean(spectral_bandwidth))
    zcr_mean = float(np.mean(zcr))
    if not np.isfinite(sc_mean):
        sc_mean = 0.0
    if not np.isfinite(sb_mean):
        sb_mean = 0.0
    if not np.isfinite(zcr_mean):
        zcr_mean = 0.0
    return {
        "mean_energy_db": mean_energy,
        "energy_std_db": energy_std,
        "spectral_centroid_mean": sc_mean,
        "spectral_bandwidth_mean": sb_mean,
        "zero_crossing_mean": zcr_mean,
    }


# Order for server/client 5-dim vector (enroll + infer)
FEATURE_ORDER = [
    "mean_energy_db",
    "energy_std_db",
    "spectral_centroid_mean",
    "spectral_bandwidth_mean",
    "zero_crossing_mean",
]


def features_to_vector(features: dict[str, float]) -> list[float]:
    """Fixed-order 5-dim vector for Vultr enroll/infer."""
    return [features[k] for k in FEATURE_ORDER]


def quick_test_summary(features: dict[str, float]) -> str:
    """Human-readable summary; low energy_std may suggest reduced prosody (hypophonia)."""
    lines = [
        f"Mean energy (dB): {features['mean_energy_db']:.1f}",
        f"Energy variation (dB): {features['energy_std_db']:.1f}",
        f"Spectral centroid (Hz): {features['spectral_centroid_mean']:.0f}",
        f"Zero-crossing rate: {features['zero_crossing_mean']:.3f}",
    ]
    if features["energy_std_db"] < 2.0:
        lines.append("\n→ Low energy variation (flat prosody) may suggest hypophonia. Run full test for baseline.")
    return "\n".join(lines)
