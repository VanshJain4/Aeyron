"""
Gradio UI: record live or upload WAV → extract features → Vultr infer → show analysis.
"""
import traceback

import gradio as gr
import librosa
import numpy as np

from pathlib import Path

from core.config import VULTR_BASE_URL, PATIENT_ID, UCI_PATIENT_ID, UCI_PD_PATIENT_ID
from core.capture import record_seconds, get_default_input_device_info
from core.quick_test import extract_quick_features, features_to_vector, FEATURE_ORDER
from core.acoustic_features import extract_features as extract_praat_features, uci_features_to_vector, UCI_FEATURE_ORDER
from core import client_network

LIVE_RECORD_SEC = 15.0  # Need 15 s for both baselines (personal 10 s + UCI 5 s + 10 s)
CHUNK_SEC = 5.0  # Must match baseline (train_baseline.py)
SAMPLE_RATE = 16000
MIN_SAMPLES_10S = int(10.0 * SAMPLE_RATE)
MIN_SAMPLES_UCI = int(15.0 * SAMPLE_RATE)  # 5s vowel + 10s speech for UCI (Praat)


def _uci_closer_to(score_healthy: float, score_pd: float) -> str:
    return "healthy" if score_healthy <= score_pd else "PD"


def _format_detailed_report(
    source_label: str,
    level: float,
    level_warning: str | None,
    personal_vec: list[float],
    out_personal: dict,
    uci_vec: list[float],
    out_healthy: dict,
    out_pd: dict,
    raw_hnr: float | None = None,
    raw_fo: float | None = None,
) -> str:
    """Single detailed report: all numbers for personal + UCI (healthy vs PD)."""
    score_healthy = out_healthy.get("anomaly_score") or 0.0
    score_pd = out_pd.get("anomaly_score") or 0.0
    uci_closer = _uci_closer_to(score_healthy, score_pd)
    th_p = out_personal.get("threshold")
    th_h = out_healthy.get("threshold")
    th_pd = out_pd.get("threshold")
    mse_p = out_personal.get("anomaly_score") or 0.0
    ratio_p = (mse_p / th_p) if th_p and th_p > 0 else None

    hnr_out_of_range = (
        raw_hnr is not None
        and len(uci_vec) == 5
        and (raw_hnr < 8.0 or raw_hnr > 33.0)
    )
    fo_corrected = (
        raw_fo is not None
        and len(uci_vec) >= 1
        and abs(uci_vec[0] - raw_fo) > 1.0
    )

    lines = [
        "═══════════════════════════════════════════════════════════════",
        "  AEGIS HYPOPHONIA — ANALYSIS REPORT",
        "═══════════════════════════════════════════════════════════════",
        "",
        f"  Source: {source_label}",
        f"  Audio level (max |sample|): {level:.6f}",
    ]
    if level_warning:
        lines.append(f"  → {level_warning}")
    lines.extend([
        "",
        "───────────────────────────────────────────────────────────────",
        "  1. PERSONAL BASELINE (your voice — librosa, first 10 s)",
        "───────────────────────────────────────────────────────────────",
        "  Features (two 5 s chunks, averaged):",
    ])
    for name, val in zip(FEATURE_ORDER, personal_vec):
        lines.append(f"    {name:28s} : {val:.6f}")
    lines.append(f"  Model threshold              : {th_p if th_p is not None else 'N/A'}")
    lines.append(f"  Reconstruction MSE          : {mse_p:.6f}")
    if ratio_p is not None:
        lines.append(f"  Score / threshold (ratio)   : {ratio_p:.4f}")
    lines.append(f"  Result                      : {out_personal.get('status', 'N/A')}")
    lines.extend([
        "",
        "───────────────────────────────────────────────────────────────",
        "  2. UCI BASELINE (healthy vs PD — Praat, 5 s vowel + 10 s speech)",
        "───────────────────────────────────────────────────────────────",
        "  Features (Fo, Fhi, Jitter, Shimmer, HNR):",
    ])
    for name, val in zip(UCI_FEATURE_ORDER, uci_vec):
        lines.append(f"    {name:28s} : {val:.6f}")
    if hnr_out_of_range:
        lines.append(f"    (HNR: raw {raw_hnr:.1f} dB out of range → set to UCI healthy mean 24.7 dB)")
    if fo_corrected and raw_fo is not None:
        lines.append(f"    (Fo: raw {raw_fo:.0f} Hz corrected to 182 Hz for UCI comparison.)")
    lines.append(f"  MSE vs healthy baseline      : {score_healthy:.6f}  (threshold: {th_h if th_h is not None else 'N/A'})")
    lines.append(f"  MSE vs PD baseline           : {score_pd:.6f}  (threshold: {th_pd if th_pd is not None else 'N/A'})")
    lines.append(f"  Closer to                    : {uci_closer} baseline")
    if th_h and th_pd and score_healthy < th_h and score_pd < th_pd:
        lines.append(f"  (Both MSEs below threshold — within normal variation for both cohorts.)")
    lines.append(f"  (Recording protocol differs from UCI; not a clinical diagnosis.)")
    lines.extend([
        "",
        "───────────────────────────────────────────────────────────────",
        "  COMBINED",
        "───────────────────────────────────────────────────────────────",
        f"  Personal : {out_personal.get('status', 'N/A')}",
        f"  UCI      : closer to {uci_closer}",
        "═══════════════════════════════════════════════════════════════",
    ])
    return "\n".join(lines)


def run_live(progress=gr.Progress()) -> tuple[str, tuple[int, np.ndarray] | None]:
    """Record 15 s → full check (personal + UCI healthy vs PD) → detailed report."""
    try:
        progress(0.15, desc="Recording 15 s...")
        samples = record_seconds(LIVE_RECORD_SEC)
        if len(samples) < MIN_SAMPLES_UCI:
            return f"Recording too short; need ≥15 s (got {len(samples)/SAMPLE_RATE:.1f} s).", None
        level = float(np.max(np.abs(samples)))
        level_warning = None
        if level < 0.001:
            level_warning = f"No signal. Device: {get_default_input_device_info()}. Run from Terminal.app and grant mic."

        progress(0.35, desc="Personal baseline...")
        n = int(CHUNK_SEC * SAMPLE_RATE)
        chunk1, chunk2 = samples[:n], samples[n : 2 * n]
        v1 = features_to_vector(extract_quick_features(chunk1, sr=SAMPLE_RATE))
        v2 = features_to_vector(extract_quick_features(chunk2, sr=SAMPLE_RATE))
        personal_vec = list(np.mean([v1, v2], axis=0))
        out_personal = client_network.infer(VULTR_BASE_URL, PATIENT_ID, personal_vec)

        progress(0.7, desc="UCI healthy vs PD...")
        task_a = samples[: int(5.0 * SAMPLE_RATE)]
        task_b = samples[int(5.0 * SAMPLE_RATE) : MIN_SAMPLES_UCI]
        feats = extract_praat_features(task_a, task_b)
        uci_vec = uci_features_to_vector(feats)
        out_healthy = client_network.infer(VULTR_BASE_URL, UCI_PATIENT_ID, uci_vec)
        out_pd = client_network.infer(VULTR_BASE_URL, UCI_PD_PATIENT_ID, uci_vec)

        report = _format_detailed_report(
            source_label="Live recording (15 s)",
            level=level,
            level_warning=level_warning,
            personal_vec=personal_vec,
            out_personal=out_personal,
            uci_vec=uci_vec,
            out_healthy=out_healthy,
            out_pd=out_pd,
            raw_hnr=feats.get("hnr"),
            raw_fo=feats.get("pitch_mean"),
        )
        return report, (SAMPLE_RATE, samples)
    except Exception as e:
        err = f"Error: {type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        if "9986" in str(e) or "PortAudio" in str(e):
            err += "\n\n→ Grant Terminal/Cursor mic in System Settings → Privacy → Microphone."
        return err, None


def run_from_file(audio_in, progress=gr.Progress()) -> str:
    """Upload one file (≥15 s) → full check (personal + UCI) → detailed report."""
    if audio_in is None:
        return "Upload a WAV file (≥15 s). One button runs all checks."
    path = audio_in if isinstance(audio_in, str) else (audio_in.get("name") or audio_in)
    if not path:
        return "Upload a WAV file."
    try:
        progress(0.15, desc="Loading audio...")
        y, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
        if len(y) < MIN_SAMPLES_UCI:
            return f"File too short; need ≥15 s (got {len(y)/SAMPLE_RATE:.1f} s)."
        level = float(np.max(np.abs(y[:MIN_SAMPLES_UCI])))
        progress(0.3, desc="Personal baseline...")
        n = int(CHUNK_SEC * SAMPLE_RATE)
        chunk1, chunk2 = y[:n], y[n : 2 * n]
        v1 = features_to_vector(extract_quick_features(chunk1, sr=SAMPLE_RATE))
        v2 = features_to_vector(extract_quick_features(chunk2, sr=SAMPLE_RATE))
        personal_vec = list(np.mean([v1, v2], axis=0))
        out_personal = client_network.infer(VULTR_BASE_URL, PATIENT_ID, personal_vec)
        progress(0.7, desc="UCI healthy vs PD...")
        task_a = y[: int(5.0 * SAMPLE_RATE)]
        task_b = y[int(5.0 * SAMPLE_RATE) : MIN_SAMPLES_UCI]
        feats = extract_praat_features(task_a, task_b)
        uci_vec = uci_features_to_vector(feats)
        out_healthy = client_network.infer(VULTR_BASE_URL, UCI_PATIENT_ID, uci_vec)
        out_pd = client_network.infer(VULTR_BASE_URL, UCI_PD_PATIENT_ID, uci_vec)
        report = _format_detailed_report(
            source_label="File (first 15 s): " + (Path(path).name if isinstance(path, str) else "uploaded"),
            level=level,
            level_warning=None,
            personal_vec=personal_vec,
            out_personal=out_personal,
            uci_vec=uci_vec,
            out_healthy=out_healthy,
            out_pd=out_pd,
            raw_hnr=feats.get("hnr"),
            raw_fo=feats.get("pitch_mean"),
        )
        return report
    except Exception as e:
        return f"Error: {e}\n\n{traceback.format_exc()}"


def show_profile() -> str:
    """Fetch and show what the trained model has (threshold, scaler range)."""
    try:
        p = client_network.get_profile(VULTR_BASE_URL, PATIENT_ID)
        lines = [
            f"Patient: {p.get('patient_id', '')}",
            f"Threshold (90th % baseline MSE): {p.get('threshold')}",
            f"Baseline loss (mean MSE on training): {p.get('baseline_loss')}",
            "Scaler min (per feature):",
        ]
        for k, v in (p.get("scaler_min") or {}).items():
            lines.append(f"  {k}: {v}")
        lines.append("Scaler max (per feature):")
        for k, v in (p.get("scaler_max") or {}).items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}\n\n{traceback.format_exc()}"


def build_ui():
    with gr.Blocks(title="Aegis Hypophonia") as demo:
        gr.Markdown("# Aegis — Voice check")
        gr.Markdown("One action runs **all** checks: personal baseline + UCI (healthy vs PD). Need **≥15 s** of audio.")
        with gr.Row():
            record_btn = gr.Button("Record live & analyze", variant="primary")
            file_in = gr.Audio(type="filepath", label="Upload WAV (≥15 s)", sources=["upload"])
        file_btn = gr.Button("Upload & analyze (all checks)", variant="primary")
        out = gr.Textbox(label="Detailed report", interactive=False, lines=28, max_lines=40)
        playback = gr.Audio(label="Recorded audio (playback)", interactive=False)
        record_btn.click(fn=run_live, inputs=[], outputs=[out, playback])
        file_btn.click(fn=run_from_file, inputs=[file_in], outputs=out)
        gr.Markdown("---")
        profile_btn = gr.Button("Show trained baseline (profile)")
        profile_out = gr.Textbox(label="Profile", interactive=False, lines=12)
        profile_btn.click(fn=show_profile, inputs=[], outputs=profile_out)
    return demo


if __name__ == "__main__":
    build_ui().launch()
