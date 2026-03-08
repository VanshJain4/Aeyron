# Aeyron — Multi-Modal Parkinson's Disease Telemetry Platform

Aeyron is a contactless, multi-modal telemetry system for early detection and continuous monitoring of Parkinson's disease symptoms. It combines three independent sensing modalities — **voice**, **cough**, and **cardiac/respiratory** — into a unified platform that requires nothing more than a microphone and a phone camera.

---

## Modules

### [Aegis Hypophonia](hypophonia/README.md) — Voice Analysis
> Targeting: [MLH] Best Use of Vultr

Real-time voice analysis detecting hypophonia (reduced vocal loudness) and speech-quality degradation. Dual-path inference: a **Vultr-hosted autoencoder** for personal baseline anomaly detection and a **local SVM classifier** (98.3% accuracy) trained on real PD voice data. Live Gradio UI with 2-second inference ticks.

**Key signals:** Spectral flatness (10x PD/healthy separation), HNR, MFCC2, voiced fraction, energy CV

### [Aegis Cough](cough/README.md) — Cough Acoustic Analysis

Acoustic cough analysis detecting motor biomarkers of PD. Hysteresis-based cough detection, 8-feature extraction per cough (spectral centroid, crest factor, phase power ratio, rise time), and weighted PD likelihood scoring calibrated against real cough recordings.

**Key signals:** Crest factor (impulsiveness), spectral centroid (turbulence frequency), rise time (expulsive force)

### [Aegis Heart](heart/README.md) — Contactless Cardiac & Respiratory Monitoring
> Targeting: [MLH] Best Use of Presage

Contactless vital signs via the **Presage SmartSpectra SDK** on iPhone. Camera-based rPPG extracts heart rate, breathing rate, and facial biomarkers (blink/talk detection) — streamed to a FastAPI backend with live clinical dashboard.

**Key signals:** Heart rate (cardiac dysautonomia), breathing rate (pneumonia risk), face emotion variance (hypomimia)

---

## Architecture Overview

```
                         AEYRON PLATFORM
    ┌──────────────────────────────────────────────────┐
    │                                                  │
    │  ┌─────────────┐  ┌──────────┐  ┌────────────┐  │
    │  │ HYPOPHONIA   │  │  COUGH   │  │   HEART    │  │
    │  │ Voice SVM +  │  │ Acoustic │  │ Presage    │  │
    │  │ Vultr AE     │  │ Features │  │ rPPG SDK   │  │
    │  └──────┬───────┘  └────┬─────┘  └─────┬──────┘  │
    │         │               │              │         │
    │         v               v              v         │
    │  ┌─────────────────────────────────────────────┐ │
    │  │           FastAPI Backend (port 8000)        │ │
    │  │  Vitals risk engine · Face emotion buffer    │ │
    │  └──────────────────────┬──────────────────────┘ │
    │                         │                        │
    │                         v                        │
    │  ┌─────────────────────────────────────────────┐ │
    │  │         Clinical Dashboard (demo.html)       │ │
    │  │  Live charts · Risk scoring · Face overlay   │ │
    │  └─────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────┘
```

---

## PD Symptoms Detected

| Symptom | Modality | Detection Method |
|---|---|---|
| Hypophonia (soft voice) | Voice | SVM classifier + autoencoder baseline drift |
| Speech quality degradation | Voice | Spectral flatness, HNR, voiced fraction |
| Weakened cough reflex | Cough | Crest factor, rise time, spectral centroid |
| Aspiration pneumonia risk | Cough + Heart | Cough PD score + breathing irregularity |
| Cardiac dysautonomia | Heart | Heart rate risk scoring, HRV analysis |
| Respiratory irregularity | Heart | Breathing rate monitoring, apnea detection |
| Hypomimia (masked face) | Heart | Face emotion variance/std over rolling window |

---

## Quick Start

### Voice + Cough Analysis
```bash
cd hypophonia/aegis_telemetry/patient_client
pip install -r requirements.txt
python3 main_ui.py
# Opens Gradio UI at http://127.0.0.1:7860
```

### Cardiac/Respiratory Monitoring
```bash
# Terminal 1: Backend
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: ngrok tunnel
ngrok http 8000

# Terminal 3: Dashboard
cd backend && python3 -m http.server 9080
# Open http://localhost:9080/demo.html

# Xcode: Build and deploy SmartSpectra demo-app to iPhone
# The iPhone streams vitals through ngrok to the dashboard
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Voice sensing | Microphone → librosa, parselmouth (Praat), scikit-learn SVM |
| Cough sensing | Microphone → scipy (hysteresis detection), librosa (features) |
| Cardiac sensing | iPhone camera → Presage SmartSpectra SDK (rPPG) |
| ML inference (cloud) | Vultr instance → PyTorch autoencoder (per-patient) |
| ML inference (local) | scikit-learn SVM (98.3% CV accuracy) |
| Backend | FastAPI + uvicorn |
| Dashboard | Vanilla HTML/CSS/JS, canvas-drawn charts |
| Tunnel | ngrok (iPhone → localhost) |
| UI (voice) | Gradio |

---

## Hackathon Compliance

- All code was written from scratch during the hackathon event period
- No pre-existing code was reused; the concept existed beforehand but all implementation is original
- External dependencies are standard open-source libraries per Rule 10
- The Presage SmartSpectra SDK is used as provided — no modification to SDK source code
- Clinical knowledge comes from published research papers — all algorithms and scoring logic were built from scratch
- Repository is public as required

---

*Aeyron — multi-modal Parkinson's disease telemetry. Voice. Cough. Heart. No wearables required.*
