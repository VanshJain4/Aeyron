"""
PD likelihood from cough acoustic features.

Clinical basis (Pitts et al. 2010; Cvejic et al. 2011; Troche et al. 2014;
Orlandic et al. 2020):
  - Parkinson's reduces expulsive force → slower rise, weaker burst
  - Reduced respiratory/laryngeal control → less turbulence (lower centroid, ZCR)
  - Less impulsive cough → lower crest factor
  - Attenuated expiratory phase → lower phase power ratio

Features and weights:
  spectral_centroid   0.22  — main turbulence indicator
  zero_crossing_rate  0.20  — airflow turbulence
  crest_factor        0.18  — impulsiveness (from detect-segment-cough)
  phase_power_ratio   0.15  — expiratory high-freq energy (from detect-segment-cough)
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
    # Healthy: broadband burst → high centroid (> 4 000 Hz)
    # PD:      narrow-band low-freq → low centroid (< 1 000 Hz)
    centroid = float(features.get("spectral_centroid", 2500.0))
    c_score = _lin(centroid, lo=1000.0, hi=4000.0, invert=True)

    # ── Zero-crossing rate (0.20) ─────────────────────────────────────────
    # Healthy: turbulent airflow → high ZCR (> 0.28)
    # PD:      smooth, quiet    → low ZCR  (< 0.10)
    zcr = float(features.get("zero_crossing_rate", 0.18))
    z_score = _lin(zcr, lo=0.10, hi=0.28, invert=True)

    # ── Crest factor (0.18) ───────────────────────────────────────────────
    # From Orlandic et al. (2020) detect-segment-cough CF feature.
    # Healthy: impulsive burst → high CF (> 5)
    # PD:      soft, gradual   → low CF  (< 2)
    cf = float(features.get("crest_factor", 3.0))
    cf_score = _lin(cf, lo=1.5, hi=5.0, invert=True)

    # ── Phase power ratio (0.15) ──────────────────────────────────────────
    # From Orlandic et al. (2020) detect-segment-cough PRE feature.
    # Healthy: expiratory phase has high-freq energy → ratio > 1.5
    # PD:      expiratory phase mostly low-freq       → ratio < 0.3
    pre = float(features.get("phase_power_ratio", 1.0))
    pre_score = _lin(pre, lo=0.2, hi=1.5, invert=True)

    # ── Rise time (0.13) ──────────────────────────────────────────────────
    # Healthy: explosive force → fast rise (< 60 ms)
    # PD:      weak muscles    → slow rise (> 200 ms)
    rt = float(features.get("rise_time", 100.0))
    r_score = _lin(rt, lo=50.0, hi=200.0, invert=False)

    # ── Peak-to-decay ratio (0.07) ────────────────────────────────────────
    # Healthy: sharp burst   → high ratio (> 0.85)
    # PD:      gradual, weak → low ratio  (< 0.45)
    pdr = float(features.get("peak_to_decay_ratio", 0.7))
    p_score = _lin(pdr, lo=0.45, hi=0.90, invert=True)

    # ── Expulsive duration (0.05) ─────────────────────────────────────────
    # Healthy: sustained expulsion → long  (> 30 ms)
    # PD:      brief, weak         → short (< 8 ms)
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
