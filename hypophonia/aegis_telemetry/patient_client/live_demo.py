"""
Real-time voice + cough detection for demo.
Mic stream → last 10 s → voice features + SVM + cough detection → live numbers + history.
Tracing: every tick appends a row to live_demo_trace.csv for drift detection.
"""
import csv
import traceback
from pathlib import Path
from collections import deque
from datetime import datetime, timezone

import warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.config import VULTR_BASE_URL, PATIENT_ID
from core.live_buffer import LiveMicBuffer
from core.quick_test import extract_quick_features, features_to_vector
from core.acoustic_features import extract_features as extract_praat_features, uci_features_to_vector
from core import client_network
from cough_analysis import run_cough_pipeline

_svm = None
_svm_scaler = None

def _get_svm():
    global _svm, _svm_scaler
    if _svm is None:
        import joblib
        model_dir = Path(__file__).resolve().parent / "core" / "models"
        _svm = joblib.load(model_dir / "local_svm.joblib")
        _svm_scaler = joblib.load(model_dir / "local_scaler.joblib")
    return _svm, _svm_scaler

SAMPLE_RATE = 16000
CHUNK_SEC = 5.0
LIVE_BUFFER_SEC = 10.0
MIN_SAMPLES = int(LIVE_BUFFER_SEC * SAMPLE_RATE)

_buffer: LiveMicBuffer | None = None

# History for graphs (max 60 ticks = 2 min at 2 s intervals)
MAX_HISTORY = 60
_history: deque[dict] = deque(maxlen=MAX_HISTORY)

# ── Tracing CSV ───────────────────────────────────────────────────────────
TRACE_LOG = Path(__file__).resolve().parent / "live_demo_trace.csv"
TRACE_HEADER = (
    "timestamp_utc", "tick_num",
    "voice_healthy_pct", "voice_pd_pct",
    "mse_personal", "th_personal", "ratio_personal", "status_personal", "risk_pct",
    "cough_count", "cough_pd_score", "cough_label",
    "cough_centroid", "cough_zcr", "cough_cf", "cough_ppr",
    "combined_pd", "combined_label",
)
_tick_num = 0


def _log_trace(data: dict) -> None:
    global _tick_num
    _tick_num += 1
    cf = data.get("cough_feats") or {}
    row = (
        datetime.now(timezone.utc).isoformat(),
        _tick_num,
        f"{data['voice_healthy_pct']:.2f}",
        f"{data['voice_pd_pct']:.2f}",
        f"{data['mse_p']:.6f}",
        f"{data['th_p']:.6f}",
        f"{data['ratio_p']:.6f}",
        data.get("status_p", ""),
        f"{data['risk_pct']:.2f}",
        data["cough_count"],
        f"{data['cough_pd_score']:.4f}" if data["cough_pd_score"] is not None else "",
        data.get("cough_label", ""),
        f"{cf.get('spectral_centroid', ''):.0f}" if cf.get("spectral_centroid") else "",
        f"{cf.get('zero_crossing_rate', ''):.4f}" if cf.get("zero_crossing_rate") else "",
        f"{cf.get('crest_factor', ''):.2f}" if cf.get("crest_factor") else "",
        f"{cf.get('phase_power_ratio', ''):.4f}" if cf.get("phase_power_ratio") else "",
        f"{data['combined_pd']:.4f}",
        data["combined_label"],
    )
    file_exists = TRACE_LOG.is_file()
    with open(TRACE_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(TRACE_HEADER)
        w.writerow(row)


def _get_buffer() -> LiveMicBuffer:
    global _buffer
    if _buffer is None:
        _buffer = LiveMicBuffer(max_seconds=20.0, sample_rate=SAMPLE_RATE)
    return _buffer


def get_history() -> list[dict]:
    return list(_history)


def clear_history():
    _history.clear()


def start_listening() -> tuple[str, bool]:
    global _tick_num
    b = _get_buffer()
    if not b.is_running():
        clear_history()
        _tick_num = 0
        b.start()
    return "Listening... speak now. Results update every 2 s.", True


def stop_listening() -> tuple[str, bool]:
    b = _get_buffer()
    if b.is_running():
        b.stop()
    return "Stopped.", False


def _risk_flagged(ratio: float) -> float:
    if ratio is None or ratio < 0:
        return 0.0
    if ratio <= 0.5:
        return 0.0
    if ratio >= 1.5:
        return 100.0
    return 100.0 * (ratio - 0.5)


def live_tick(running: bool) -> tuple[str, object, object, object]:
    """
    Called every 2 s. Returns (markdown, voice_plot, cough_plot, combined_plot).
    Plots are matplotlib figures or None.
    """
    empty_fig = _empty_figure("Waiting for data...")

    if not running:
        return (
            "**Live demo stopped.** Click **Start** to speak and see real-time results.",
            empty_fig, empty_fig, empty_fig,
        )
    b = _get_buffer()
    if not b.is_running():
        return "Click **Start** to begin.", empty_fig, empty_fig, empty_fig

    samples = b.get_last_seconds(LIVE_BUFFER_SEC)
    if samples is None:
        sec = b.seconds_available()
        return (
            f"**Collecting audio...** {sec:.1f} s (need {LIVE_BUFFER_SEC:.0f} s). Keep speaking.",
            empty_fig, empty_fig, empty_fig,
        )

    try:
        # ── Voice analysis (SVM) ──
        n = int(CHUNK_SEC * SAMPLE_RATE)
        chunk1, chunk2 = samples[:n], samples[n:MIN_SAMPLES]
        v1 = features_to_vector(extract_quick_features(chunk1, sr=SAMPLE_RATE))
        v2 = features_to_vector(extract_quick_features(chunk2, sr=SAMPLE_RATE))
        personal_vec = list(np.mean([v1, v2], axis=0))
        out_p = client_network.infer(VULTR_BASE_URL, PATIENT_ID, personal_vec)

        task_a = samples[:n]
        task_b = samples[n:MIN_SAMPLES]
        feats = extract_praat_features(task_a, task_b)
        uci_vec = uci_features_to_vector(feats)

        svm, svm_scaler = _get_svm()
        uci_arr = svm_scaler.transform([uci_vec])
        proba = svm.predict_proba(uci_arr)[0]
        p_healthy = 100.0 * proba[0]
        p_pd = 100.0 * proba[1]
        voice_closer = "healthy" if p_healthy >= p_pd else "PD"

        mse_p = out_p.get("anomaly_score") or 0.0
        th_p = out_p.get("threshold") or 1e-9
        ratio_p = mse_p / th_p
        status_p = out_p.get("status", "-")
        risk_pct = _risk_flagged(ratio_p)

        # ── Cough analysis ──
        cough_result = run_cough_pipeline(samples, sr=SAMPLE_RATE)
        cough_count = cough_result["cough_count"]
        cough_pd_score = cough_result["pd_score"]
        cough_label = cough_result["pd_label"]
        cough_feats = cough_result["features"]

        # ── Combined score ──
        voice_pd_pct = p_pd
        if cough_pd_score is not None:
            combined_pd = 0.55 * (voice_pd_pct / 100.0) + 0.45 * cough_pd_score
            combined_label = (
                "LOW_RISK" if combined_pd < 0.35
                else "MODERATE_RISK" if combined_pd < 0.60
                else "HIGH_RISK"
            )
        else:
            combined_pd = voice_pd_pct / 100.0
            combined_label = (
                "LOW_RISK" if combined_pd < 0.35
                else "MODERATE_RISK" if combined_pd < 0.60
                else "HIGH_RISK"
            )

        # ── Save to history ──
        tick_data = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "voice_pd_pct": p_pd,
            "voice_healthy_pct": p_healthy,
            "cough_pd_score": cough_pd_score,
            "cough_count": cough_count,
            "combined_pd": combined_pd,
            "mse_p": mse_p,
            "th_p": th_p,
            "ratio_p": ratio_p,
            "risk_pct": risk_pct,
        }
        _history.append(tick_data)

        # ── Trace log (CSV for drift detection) ──
        _log_trace({
            **tick_data,
            "status_p": status_p,
            "cough_label": cough_label,
            "cough_feats": cough_feats,
            "combined_label": combined_label,
        })

        # ── Build plots (close old figs to prevent memory leak) ──
        plt.close("all")
        voice_fig = _make_voice_plot(list(_history))
        cough_fig = _make_cough_plot(list(_history))
        combined_fig = _make_combined_plot(list(_history))

        # ── Build markdown ──
        md = _build_markdown(
            p_healthy, p_pd, voice_closer, status_p, mse_p, th_p, ratio_p, risk_pct,
            cough_count, cough_pd_score, cough_label, cough_feats,
            combined_pd, combined_label,
        )

        return md, voice_fig, cough_fig, combined_fig

    except Exception as e:
        return (
            f"**Error:** {e}\n\n```\n{traceback.format_exc()}\n```",
            empty_fig, empty_fig, empty_fig,
        )


def _build_markdown(
    p_healthy, p_pd, voice_closer, status_p, mse_p, th_p, ratio_p, risk_pct,
    cough_count, cough_pd_score, cough_label, cough_feats,
    combined_pd, combined_label,
) -> str:
    lines = [
        "## LIVE - Voice + Cough Analysis\n",
        "### SVM Voice Classification (98% accuracy)\n",
        "|  |  |",
        "|--|--|",
        f"| **Result** | **{voice_closer.upper()}** |",
        f"| Healthy probability | {p_healthy:.1f}% |",
        f"| PD probability | {p_pd:.1f}% |",
        "",
        "### Personal Baseline (Vultr autoencoder)\n",
        "|  |  |",
        "|--|--|",
        f"| MSE | {mse_p:.6f} |",
        f"| Threshold | {th_p:.6f} |",
        f"| Ratio | {ratio_p:.3f} |",
        f"| Status | **{status_p}** |",
        f"| Risk % | **{risk_pct:.0f}%** |",
        "",
    ]

    if cough_count > 0 and cough_pd_score is not None:
        lines.extend([
            f"### Cough Analysis ({cough_count} cough{'s' if cough_count != 1 else ''} detected)\n",
            "|  |  |",
            "|--|--|",
            f"| PD Score | **{cough_pd_score:.1%}** |",
            f"| Label | **{cough_label}** |",
        ])
        if cough_feats:
            lines.extend([
                f"| Spectral Centroid | {cough_feats['spectral_centroid']:.0f} Hz |",
                f"| Crest Factor | {cough_feats['crest_factor']:.2f} |",
                f"| ZCR | {cough_feats['zero_crossing_rate']:.4f} |",
            ])
        lines.append("")
    else:
        lines.extend([
            "### Cough Analysis\n",
            "*No cough detected. Cough into the mic for cough-based PD analysis.*\n",
        ])

    risk_emoji = "LOW" if combined_label == "LOW_RISK" else "MODERATE" if combined_label == "MODERATE_RISK" else "HIGH"
    lines.extend([
        "---\n",
        f"### Combined PD Likelihood: **{combined_pd:.1%}** ({risk_emoji})",
        f"*{'Voice + Cough' if cough_count > 0 else 'Voice only (no cough detected)'}*",
    ])

    return "\n".join(lines)


def _empty_figure(text: str):
    plt.close("all")
    fig, ax = plt.subplots(figsize=(5, 2.5))
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=12, color="#888")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    return fig


def _make_voice_plot(history: list[dict]):
    if len(history) < 2:
        return _empty_figure("Collecting voice data...")

    times = [h["time"] for h in history]
    healthy = [h["voice_healthy_pct"] for h in history]
    pd_pct = [h["voice_pd_pct"] for h in history]

    fig, ax = plt.subplots(figsize=(5, 2.5))
    ax.fill_between(range(len(times)), healthy, alpha=0.3, color="#22c55e")
    ax.fill_between(range(len(times)), pd_pct, alpha=0.3, color="#ef4444")
    ax.plot(range(len(times)), healthy, color="#22c55e", linewidth=2, label="Healthy %")
    ax.plot(range(len(times)), pd_pct, color="#ef4444", linewidth=2, label="PD %")
    ax.set_ylim(0, 100)
    ax.set_ylabel("%", fontsize=9)
    ax.set_title("Voice SVM Classification", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    _style_axis(ax, times)
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    return fig


def _make_cough_plot(history: list[dict]):
    cough_ticks = [h for h in history if h["cough_pd_score"] is not None]
    if len(cough_ticks) < 1:
        return _empty_figure("No cough detected yet - cough into the mic")

    times = [h["time"] for h in cough_ticks]
    scores = [h["cough_pd_score"] * 100 for h in cough_ticks]
    counts = [h["cough_count"] for h in cough_ticks]

    fig, ax = plt.subplots(figsize=(5, 2.5))
    colors = ["#22c55e" if s < 35 else "#f59e0b" if s < 60 else "#ef4444" for s in scores]
    ax.bar(range(len(times)), scores, color=colors, alpha=0.8, width=0.6)
    for i, c in enumerate(counts):
        ax.text(i, scores[i] + 2, f"{c}x", ha="center", fontsize=7, color="#666")
    ax.axhline(35, color="#22c55e", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(60, color="#ef4444", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("PD Score %", fontsize=9)
    ax.set_title("Cough PD Likelihood", fontsize=10, fontweight="bold")
    _style_axis(ax, times)
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    return fig


def _make_combined_plot(history: list[dict]):
    if len(history) < 2:
        return _empty_figure("Collecting data...")

    times = [h["time"] for h in history]
    combined = [h["combined_pd"] * 100 for h in history]

    fig, ax = plt.subplots(figsize=(5, 2.5))
    ax.fill_between(range(len(times)), combined, alpha=0.15, color="#6366f1")
    ax.plot(range(len(times)), combined, color="#6366f1", linewidth=2.5)
    for i, v in enumerate(combined):
        if v < 35:
            c = "#22c55e"
        elif v < 60:
            c = "#f59e0b"
        else:
            c = "#ef4444"
        ax.scatter(i, v, color=c, s=20, zorder=5)
    ax.axhline(35, color="#22c55e", linestyle="--", linewidth=0.8, alpha=0.5, label="Low/Mod")
    ax.axhline(60, color="#ef4444", linestyle="--", linewidth=0.8, alpha=0.5, label="Mod/High")
    ax.set_ylim(0, 100)
    ax.set_ylabel("PD %", fontsize=9)
    ax.set_title("Combined PD Likelihood", fontsize=10, fontweight="bold")
    ax.legend(fontsize=7, loc="upper right")
    _style_axis(ax, times)
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    return fig


def _style_axis(ax, times):
    ax.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#ddd")
    ax.spines["bottom"].set_color("#ddd")
    ax.tick_params(colors="#888", labelsize=7)
    ax.grid(axis="y", alpha=0.2)
    n = len(times)
    if n <= 10:
        ax.set_xticks(range(n))
        ax.set_xticklabels(times, rotation=45, fontsize=6)
    else:
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([times[i] for i in ticks], rotation=45, fontsize=6)
