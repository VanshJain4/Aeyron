"""
PD likelihood from cough acoustic features.

Clinical basis (Pitts et al. 2010; Cvejic et al. 2011; Troche et al. 2014):
  - Parkinson's reduces expulsive force → slower rise, weaker burst
  - Reduced respiratory/laryngeal control → less turbulence, lower spectral centroid
  - Shorter voluntary cough peak flow → brief expulsive phase
  - Less high-frequency energy in cough → lower ZCR, lower centroid

Each feature is mapped to a 0-1 PD indicator score via piecewise linear thresholds.
Weighted combination → final pd_score (0 = healthy-like, 1 = PD-like).
"""
from __future__ import annotations


def _lin(x: float, lo: float, hi: float, invert: bool = False) -> float:
    """Linear map: x in [lo, hi] → [0, 1]. Clamps outside range."""
    if hi == lo:
        return 0.0
    t = (x - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return (1.0 - t) if invert else t


def pd_likelihood(features: dict) -> tuple[float, str]:
    """
    Compute PD likelihood from averaged cough features.

    Args:
        features: dict with keys from features.py (spectral_centroid,
                  zero_crossing_rate, rise_time, peak_to_decay_ratio,
                  expulsive_duration, spectral_slope)

    Returns:
        (pd_score, label)
        pd_score: 0.0 (healthy-like) to 1.0 (PD-like)
        label:    "LOW_RISK" | "MODERATE_RISK" | "HIGH_RISK"
    """
    # ── Spectral centroid (weight 0.30) ────────────────────────────────
    # Healthy: broadband burst → high centroid (> 4 000 Hz)
    # PD:      narrow-band low-freq → low centroid (< 1 000 Hz)
    centroid = float(features.get("spectral_centroid", 2500.0))
    c_score = _lin(centroid, lo=1000.0, hi=4000.0, invert=True)

    # ── Zero-crossing rate (weight 0.25) ───────────────────────────────
    # Healthy: turbulent airflow → high ZCR (> 0.28)
    # PD:      smooth, quiet    → low ZCR (< 0.10)
    zcr = float(features.get("zero_crossing_rate", 0.18))
    z_score = _lin(zcr, lo=0.10, hi=0.28, invert=True)

    # ── Rise time (weight 0.20) ────────────────────────────────────────
    # Healthy: explosive force → fast rise (< 60 ms)
    # PD:      weak muscles    → slow rise (> 200 ms)
    rt = float(features.get("rise_time", 100.0))
    r_score = _lin(rt, lo=50.0, hi=200.0, invert=False)

    # ── Peak-to-decay ratio (weight 0.15) ──────────────────────────────
    # Healthy: sharp burst, quick decay → high ratio (> 0.85)
    # PD:      gradual, weak            → low ratio (< 0.45)
    pdr = float(features.get("peak_to_decay_ratio", 0.7))
    p_score = _lin(pdr, lo=0.45, hi=0.90, invert=True)

    # ── Expulsive duration (weight 0.10) ───────────────────────────────
    # Healthy: sustained expulsion → long (> 30 ms)
    # PD:      brief, weak        → short (< 8 ms)
    ed = float(features.get("expulsive_duration", 20.0))
    e_score = _lin(ed, lo=8.0, hi=35.0, invert=True)

    pd_score = (
        0.30 * c_score +
        0.25 * z_score +
        0.20 * r_score +
        0.15 * p_score +
        0.10 * e_score
    )
    pd_score = max(0.0, min(1.0, pd_score))

    if pd_score < 0.35:
        label = "LOW_RISK"
    elif pd_score < 0.60:
        label = "MODERATE_RISK"
    else:
        label = "HIGH_RISK"

    return round(pd_score, 4), label
