"""
PD likelihood from cough acoustic features.

Clinical basis: Parkinson's degrades respiratory and laryngeal muscle control,
producing measurably weaker, slower, and less turbulent coughs:
  - Reduced expulsive force → slower rise, weaker burst
  - Less respiratory/laryngeal control → less turbulence (lower centroid, ZCR)
  - Less impulsive cough → lower crest factor
  - Attenuated expiratory phase → lower phase power ratio

Thresholds are calibrated for REAL human cough audio (not synthetic):
  Healthy cough:  centroid 1200-2500 Hz, ZCR 0.10-0.18, CF 5-9, PRE 0.6-2.0
  PD cough:       centroid 400-900 Hz,   ZCR 0.03-0.07, CF 2-4, PRE 0.1-0.4

Features and weights:
  spectral_centroid   0.22  — main turbulence indicator
  zero_crossing_rate  0.20  — airflow turbulence
  crest_factor        0.18  — impulsiveness
  phase_power_ratio   0.15  — expiratory high-freq energy
  rise_time           0.13  — expulsive speed
  peak_to_decay_ratio 0.07  — burst sharpness
  expulsive_duration  0.05  — sustained expulsion
"""
from __future__ import annotations


def _lin(x: float, lo: float, hi: float, invert: bool = False) -> float:
    """Piecewise linear map: x in [lo, hi] → [0, 1], clamped."""
    if hi == lo:
        return 0.0
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return (1.0 - t) if invert else t


def pd_likelihood(features: dict) -> tuple[float, str]:
    """
    Compute PD likelihood from averaged cough features.

    Args:
        features: dict with keys produced by features.extract_features()

    Returns:
        (pd_score, label)
        pd_score : 0.0 (healthy-like) → 1.0 (PD-like)
        label    : "LOW_RISK" | "MODERATE_RISK" | "HIGH_RISK"
    """
    # ── Spectral centroid (0.22) ──────────────────────────────────────────
    # Real healthy cough: 1200-2500 Hz (glottal turbulence + vocal tract resonance)
    # Real PD cough:       400-900 Hz  (less turbulence, lower freq dominant)
    centroid = float(features.get("spectral_centroid", 1200.0))
    c_score = _lin(centroid, lo=600.0, hi=1800.0, invert=True)

    # ── Zero-crossing rate (0.20) ─────────────────────────────────────────
    # Real healthy: 0.10-0.18 (turbulent airflow)
    # Real PD:      0.03-0.07 (smoother, weaker airflow)
    zcr = float(features.get("zero_crossing_rate", 0.10))
    z_score = _lin(zcr, lo=0.04, hi=0.14, invert=True)

    # ── Crest factor (0.18) ───────────────────────────────────────────────
    # Real healthy: 5-9. Real PD: 2-4.5
    cf = float(features.get("crest_factor", 4.0))
    cf_score = _lin(cf, lo=2.5, hi=6.5, invert=True)

    # ── Phase power ratio (0.15) ──────────────────────────────────────────
    # Real healthy: 0.5-2.0+. Real PD: 0.1-0.4
    pre = float(features.get("phase_power_ratio", 0.5))
    pre_score = _lin(pre, lo=0.15, hi=0.7, invert=True)

    # ── Rise time (0.13) ──────────────────────────────────────────────────
    # Healthy: < 60 ms. PD: > 180 ms.
    rt = float(features.get("rise_time", 80.0))
    r_score = _lin(rt, lo=50.0, hi=200.0, invert=False)

    # ── Peak-to-decay ratio (0.07) ────────────────────────────────────────
    # Healthy: sharp burst → ratio > 0.85. PD: gradual → ratio < 0.45.
    pdr = float(features.get("peak_to_decay_ratio", 0.7))
    p_score = _lin(pdr, lo=0.45, hi=0.90, invert=True)

    # ── Expulsive duration (0.05) ─────────────────────────────────────────
    # Healthy: > 30 ms. PD: < 8 ms.
    ed = float(features.get("expulsive_duration", 20.0))
    e_score = _lin(ed, lo=8.0, hi=35.0, invert=True)

    pd_score = (
        0.22 * c_score +
        0.20 * z_score +
        0.18 * cf_score +
        0.15 * pre_score +
        0.13 * r_score +
        0.07 * p_score +
        0.05 * e_score
    )
    pd_score = max(0.0, min(1.0, pd_score))

    if pd_score < 0.35:
        label = "LOW_RISK"
    elif pd_score < 0.60:
        label = "MODERATE_RISK"
    else:
        label = "HIGH_RISK"

    return round(pd_score, 4), label
