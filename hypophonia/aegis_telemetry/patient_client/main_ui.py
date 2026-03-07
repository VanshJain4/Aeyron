"""
Gradio UI: combined voice + cough PD analysis with live graphs.
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
from cough_analysis import run_cough_pipeline
from live_demo import start_listening, stop_listening, live_tick

LIVE_RECORD_SEC = 15.0
CHUNK_SEC = 5.0
SAMPLE_RATE = 16000
MIN_SAMPLES_10S = int(10.0 * SAMPLE_RATE)
MIN_SAMPLES_UCI = int(15.0 * SAMPLE_RATE)

# ── White/clean CSS theme ─────────────────────────────────────────────────

CUSTOM_CSS = """
.gradio-container {
    background: #ffffff !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    max-width: 1100px;
    margin: 0 auto;
}
.gr-button-primary {
    background: #6366f1 !important;
    border: none !important;
    color: white !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
.gr-button-secondary {
    background: #f1f5f9 !important;
    border: 1px solid #e2e8f0 !important;
    color: #334155 !important;
    border-radius: 8px !important;
}
.gr-button-stop {
    background: #fee2e2 !important;
    border: 1px solid #fecaca !important;
    color: #dc2626 !important;
    border-radius: 8px !important;
}
footer { display: none !important; }
.gr-panel { border-radius: 12px !important; }
h1 { color: #1e293b !important; font-weight: 700 !important; }
h2, h3 { color: #334155 !important; }
.label-wrap { font-weight: 600 !important; color: #475569 !important; }
"""


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
    cough_result: dict | None = None,
) -> str:
    score_healthy = out_healthy.get("anomaly_score") or 0.0
    score_pd = out_pd.get("anomaly_score") or 0.0
    uci_closer = _uci_closer_to(score_healthy, score_pd)
    th_p = out_personal.get("threshold")
    th_h = out_healthy.get("threshold")
    th_pd = out_pd.get("threshold")
    mse_p = out_personal.get("anomaly_score") or 0.0
    ratio_p = (mse_p / th_p) if th_p and th_p > 0 else None

    lines = [
        "## Aegis Hypophonia - Analysis Report\n",
        f"**Source:** {source_label}  ",
        f"**Audio level:** {level:.6f}\n",
    ]
    if level_warning:
        lines.append(f"> {level_warning}\n")

    lines.extend([
        "### 1. Personal Baseline (librosa, first 10 s)\n",
        "| Feature | Value |",
        "|---------|-------|",
    ])
    for name, val in zip(FEATURE_ORDER, personal_vec):
        lines.append(f"| {name} | {val:.6f} |")
    lines.extend([
        f"\n**Threshold:** {th_p if th_p is not None else 'N/A'}  ",
        f"**MSE:** {mse_p:.6f}  ",
    ])
    if ratio_p is not None:
        lines.append(f"**Ratio:** {ratio_p:.4f}  ")
    lines.append(f"**Result:** {out_personal.get('status', 'N/A')}\n")

    lines.extend([
        "### 2. UCI Baseline (Praat, 5 s vowel + 10 s speech)\n",
        "| Feature | Value |",
        "|---------|-------|",
    ])
    for name, val in zip(UCI_FEATURE_ORDER, uci_vec):
        lines.append(f"| {name} | {val:.4f} |")

    lines.append(f"\n**MSE vs healthy:** {score_healthy:.6f} (threshold: {th_h if th_h is not None else 'N/A'})  ")
    lines.append(f"**MSE vs PD:** {score_pd:.6f} (threshold: {th_pd if th_pd is not None else 'N/A'})  ")

    both_uci_below = th_h and th_pd and score_healthy < th_h and score_pd < th_pd
    if both_uci_below:
        lines.append("**Result:** Within normal variation for both cohorts\n")
    else:
        lines.append(f"**Closer to:** {uci_closer} baseline\n")

    # Cough section
    if cough_result and cough_result["cough_count"] > 0 and cough_result["pd_score"] is not None:
        lines.extend([
            f"### 3. Cough Analysis ({cough_result['cough_count']} coughs detected)\n",
            "| Feature | Value |",
            "|---------|-------|",
        ])
        if cough_result["features"]:
            cf = cough_result["features"]
            lines.append(f"| Spectral Centroid | {cf['spectral_centroid']:.0f} Hz |")
            lines.append(f"| ZCR | {cf['zero_crossing_rate']:.4f} |")
            lines.append(f"| Crest Factor | {cf['crest_factor']:.2f} |")
            lines.append(f"| Phase Power Ratio | {cf['phase_power_ratio']:.4f} |")
            lines.append(f"| Rise Time | {cf['rise_time']:.1f} ms |")
        lines.append(f"\n**PD Score:** {cough_result['pd_score']:.1%}  ")
        lines.append(f"**Label:** {cough_result['pd_label']}\n")
    else:
        lines.extend([
            "### 3. Cough Analysis\n",
            "*No cough detected in audio. Include coughs for multi-modal analysis.*\n",
        ])

    # Combined
    uci_summary = "within normal (both cohorts)" if both_uci_below else f"closer to {uci_closer}"
    lines.extend([
        "---\n",
        "### Summary\n",
        f"- **Personal baseline:** {out_personal.get('status', 'N/A')}",
        f"- **UCI comparison:** {uci_summary}",
    ])
    if cough_result and cough_result["pd_score"] is not None:
        lines.append(f"- **Cough PD score:** {cough_result['pd_score']:.1%} ({cough_result['pd_label']})")
    lines.append("\n*(Not a clinical diagnosis.)*")
    return "\n".join(lines)


def run_live(progress=gr.Progress()) -> tuple[str, tuple[int, np.ndarray] | None]:
    """Record 15 s -> full check (personal + UCI + cough) -> report."""
    try:
        progress(0.1, desc="Recording 15 s...")
        samples = record_seconds(LIVE_RECORD_SEC)
        if len(samples) < MIN_SAMPLES_UCI:
            return f"Recording too short; need >= 15 s (got {len(samples)/SAMPLE_RATE:.1f} s).", None
        level = float(np.max(np.abs(samples)))
        level_warning = None
        if level < 0.001:
            level_warning = f"No signal. Device: {get_default_input_device_info()}. Run from Terminal.app and grant mic."

        progress(0.3, desc="Personal baseline...")
        n = int(CHUNK_SEC * SAMPLE_RATE)
        chunk1, chunk2 = samples[:n], samples[n : 2 * n]
        v1 = features_to_vector(extract_quick_features(chunk1, sr=SAMPLE_RATE))
        v2 = features_to_vector(extract_quick_features(chunk2, sr=SAMPLE_RATE))
        personal_vec = list(np.mean([v1, v2], axis=0))
        out_personal = client_network.infer(VULTR_BASE_URL, PATIENT_ID, personal_vec)

        progress(0.55, desc="UCI healthy vs PD...")
        task_a = samples[: int(5.0 * SAMPLE_RATE)]
        task_b = samples[int(5.0 * SAMPLE_RATE) : MIN_SAMPLES_UCI]
        feats = extract_praat_features(task_a, task_b)
        uci_vec = uci_features_to_vector(feats)
        out_healthy = client_network.infer(VULTR_BASE_URL, UCI_PATIENT_ID, uci_vec)
        out_pd = client_network.infer(VULTR_BASE_URL, UCI_PD_PATIENT_ID, uci_vec)

        progress(0.8, desc="Cough detection...")
        cough_result = run_cough_pipeline(samples, sr=SAMPLE_RATE)

        report = _format_detailed_report(
            source_label="Live recording (15 s)",
            level=level,
            level_warning=level_warning,
            personal_vec=personal_vec,
            out_personal=out_personal,
            uci_vec=uci_vec,
            out_healthy=out_healthy,
            out_pd=out_pd,
            cough_result=cough_result,
        )
        return report, (SAMPLE_RATE, samples)
    except Exception as e:
        err = f"Error: {type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        if "9986" in str(e) or "PortAudio" in str(e):
            err += "\n\n> Grant microphone access in System Settings > Privacy > Microphone."
        return err, None


def _audio_input_to_path(audio_in):
    if audio_in is None:
        return None
    if isinstance(audio_in, str):
        return audio_in.strip() or None
    if isinstance(audio_in, dict):
        return (audio_in.get("name") or audio_in.get("path")) or None
    if isinstance(audio_in, (list, tuple)) and audio_in:
        return _audio_input_to_path(audio_in[0])
    return None


def run_from_file(audio_in, progress=gr.Progress()) -> tuple[str, str | None]:
    """Upload one file (>= 15 s) -> full check (personal + UCI + cough) -> report."""
    path = _audio_input_to_path(audio_in)
    if not path:
        return "Upload a WAV file (>= 15 s). One button runs all checks.", None
    path = str(Path(path).resolve())
    try:
        progress(0.1, desc="Loading audio...")
        y, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
        if len(y) < MIN_SAMPLES_UCI:
            return f"File too short; need >= 15 s (got {len(y)/SAMPLE_RATE:.1f} s).", None
        level = float(np.max(np.abs(y[:MIN_SAMPLES_UCI])))

        progress(0.25, desc="Personal baseline...")
        n = int(CHUNK_SEC * SAMPLE_RATE)
        chunk1, chunk2 = y[:n], y[n : 2 * n]
        v1 = features_to_vector(extract_quick_features(chunk1, sr=SAMPLE_RATE))
        v2 = features_to_vector(extract_quick_features(chunk2, sr=SAMPLE_RATE))
        personal_vec = list(np.mean([v1, v2], axis=0))
        out_personal = client_network.infer(VULTR_BASE_URL, PATIENT_ID, personal_vec)

        progress(0.55, desc="UCI healthy vs PD...")
        task_a = y[: int(5.0 * SAMPLE_RATE)]
        task_b = y[int(5.0 * SAMPLE_RATE) : MIN_SAMPLES_UCI]
        feats = extract_praat_features(task_a, task_b)
        uci_vec = uci_features_to_vector(feats)
        out_healthy = client_network.infer(VULTR_BASE_URL, UCI_PATIENT_ID, uci_vec)
        out_pd = client_network.infer(VULTR_BASE_URL, UCI_PD_PATIENT_ID, uci_vec)

        progress(0.8, desc="Cough detection...")
        cough_result = run_cough_pipeline(y, sr=SAMPLE_RATE)

        report = _format_detailed_report(
            source_label="File (first 15 s): " + Path(path).name,
            level=level,
            level_warning=None,
            personal_vec=personal_vec,
            out_personal=out_personal,
            uci_vec=uci_vec,
            out_healthy=out_healthy,
            out_pd=out_pd,
            cough_result=cough_result,
        )
        return report, None
    except Exception as e:
        return f"Error: {e}\n\n{traceback.format_exc()}", None


def show_profile() -> str:
    try:
        p = client_network.get_profile(VULTR_BASE_URL, PATIENT_ID)
        lines = [
            f"**Patient:** {p.get('patient_id', '')}  ",
            f"**Threshold:** {p.get('threshold')}  ",
            f"**Baseline loss:** {p.get('baseline_loss')}  ",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}\n\n{traceback.format_exc()}"


def build_ui():
    with gr.Blocks(
        title="Aegis - Hypophonia + Cough PD Detection",
    ) as demo:
        gr.Markdown(
            "# Aegis - Parkinson's Voice & Cough Analysis\n"
            "Multi-modal PD detection: voice SVM classification + cough acoustic analysis. "
            "Results update every 2 seconds."
        )

        with gr.Tabs():
            # ── Tab 1: Live demo with graphs ──
            with gr.TabItem("Live Analysis"):
                gr.Markdown(
                    "**Start** the mic, then speak normally for 10 s. "
                    "**Cough** into the mic for cough-based PD analysis. "
                    "If no cough is detected, voice-only results are shown."
                )
                with gr.Row():
                    start_btn = gr.Button("Start", variant="primary", scale=1)
                    stop_btn = gr.Button("Stop", variant="stop", scale=1)

                live_display = gr.Markdown(
                    value="Click **Start** to begin. Speak and cough for full multi-modal analysis."
                )

                gr.Markdown("### Real-time Graphs")
                with gr.Row():
                    voice_plot = gr.Plot(label="Voice Classification")
                    cough_plot = gr.Plot(label="Cough PD Score")
                with gr.Row():
                    combined_plot = gr.Plot(label="Combined PD Likelihood")

                running_state = gr.State(value=False)
                start_btn.click(fn=start_listening, inputs=[], outputs=[live_display, running_state])
                stop_btn.click(fn=stop_listening, inputs=[], outputs=[live_display, running_state])
                timer = gr.Timer(value=2)
                timer.tick(
                    fn=live_tick,
                    inputs=[running_state],
                    outputs=[live_display, voice_plot, cough_plot, combined_plot],
                )

            # ── Tab 2: Record once ──
            with gr.TabItem("Record Once (15 s)"):
                gr.Markdown(
                    "Records 15 s from mic -> full analysis including cough detection.\n\n"
                    "**First 5 s** -> say 'Ahhhh' (vowel for Praat).  "
                    "**Next 10 s** -> speak freely + cough if possible."
                )
                record_btn = gr.Button("Record 15 s & Analyze", variant="primary")
                out = gr.Markdown(label="Report")
                playback = gr.Audio(label="Playback", interactive=False)
                record_btn.click(fn=run_live, inputs=[], outputs=[out, playback])

                gr.Markdown("---")
                profile_btn = gr.Button("Show enrolled baseline profile")
                profile_out = gr.Markdown(label="Profile")
                profile_btn.click(fn=show_profile, inputs=[], outputs=profile_out)

            # ── Tab 3: Upload file ──
            with gr.TabItem("Upload File"):
                gr.Markdown(
                    "Upload a WAV file (>= 15 s). Runs voice + cough analysis on the full audio."
                )
                audio_upload = gr.Audio(label="Upload audio", type="filepath")
                upload_btn = gr.Button("Analyze", variant="primary")
                upload_out = gr.Markdown(label="Report")
                upload_btn.click(fn=run_from_file, inputs=[audio_upload], outputs=[upload_out, audio_upload])

    return demo


if __name__ == "__main__":
    build_ui().launch(
        strict_cors=False,
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(
            primary_hue="indigo",
            secondary_hue="slate",
            neutral_hue="slate",
            font=("Inter", "system-ui", "sans-serif"),
        ),
    )
