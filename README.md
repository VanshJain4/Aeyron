# AEYRON Sentinel

### Contactless, Multi-Modal Parkinson's Disease Detection — Using Nothing But a Mic and a Phone Camera

> **What if your phone could detect Parkinson's disease before you even notice the symptoms?**

Aeyron Sentinel is a real-time telemetry platform that listens to your **voice**, analyzes your **cough**, reads your **heartbeat** through your phone camera, and watches your **facial expressions** — all without a single wearable device. It fuses these four independent biomarker streams into one unified PD risk score, updated every 2 seconds, displayed on a live clinical dashboard.

No blood draws. No lab visits. No special hardware. Just speak, cough, and look at your phone.

---

## The Problem

**10 million people** worldwide live with Parkinson's disease. By the time motor symptoms are clinically obvious — tremor, rigidity, slow movement — up to **80% of dopamine-producing neurons are already lost**. Early detection is everything, but current methods require expensive imaging (DaTscan), specialist visits, and subjective clinical assessments.

Meanwhile, **subtle biomarkers appear years before diagnosis:**
- Voice gets quieter (hypophonia) and speech quality degrades
- Cough reflex weakens, raising pneumonia risk
- Heart rate variability drops (cardiac dysautonomia)
- Facial expressions flatten (hypomimia / "masked face")

These signals are hiding in plain sight — in every phone call, every cough, every selfie. We built a system to catch them.

---

## How It Works

```
 YOUR VOICE          YOUR COUGH         YOUR PHONE CAMERA        YOUR WEBCAM
     |                   |                     |                      |
     v                   v                     v                      v
 [Microphone]       [Microphone]         [iPhone Camera]        [Browser Webcam]
     |                   |                     |                      |
     v                   v                     v                      v
 Praat + librosa     Hysteresis          Presage SmartSpectra    face-api.js
 feature extraction  cough detection     rPPG SDK                expression detection
     |                   |                     |                      |
     v                   v                     v                      v
 SVM Classifier      8-feature PD        Heart rate, HRV,        Emotion confidence
 (98.3% accuracy)    likelihood scoring   breathing rate          variance tracking
 + Vultr Autoencoder                     + stress score           (hypomimia detection)
     |                   |                     |                      |
     +-------------------+---------------------+----------------------+
                                  |
                                  v
                    FastAPI Backend (port 8000)
                    /voice  /cough  /vitals  /status
                                  |
                                  v
                    Combined PD Risk Score (0-100)
                    Weighted: Voice 30% | Heart 25% | Cough 25% | Face 20%
                                  |
                                  v
                    Live Clinical Dashboard
                    Real-time charts, modality badges, risk alerts
```

### Four Modalities, One Score

| Modality | What It Detects | How | Accuracy/Validation |
|---|---|---|---|
| **Voice** | Hypophonia, speech degradation | Dual-path: RBF-SVM on UCI features + Vultr autoencoder for personal drift | **98.3% CV accuracy** (SVM), longitudinal anomaly detection (AE) |
| **Cough** | Weakened expulsive force, aspiration risk | Hysteresis detection + 8 acoustic features + weighted PD scoring | Calibrated against real cough recordings (healthy: 27-33%, PD-like: 55-71%) |
| **Heart** | Cardiac dysautonomia, respiratory irregularity | iPhone camera rPPG via Presage SDK — extracts HR, HRV, breathing rate | Clinical-grade Presage SDK, risk formula: `(HR_risk * 0.35) + (HRV_risk * 0.35) + (stress * 0.30)` |
| **Face** | Hypomimia (masked face) | Browser webcam + face-api.js expression detection, rolling variance of emotion confidence | Flags when expression variance drops below clinical thresholds |

The combined score dynamically renormalizes weights based on which modalities are active — if you only have a mic, voice and cough still work. Add a phone camera, heart joins in. Open the dashboard with a webcam, face lights up. **It degrades gracefully.**

---

## Why This Matters

### For Patients
- **Screen yourself at home** — no appointment needed
- **Track progression over time** — personal baselines detect YOUR drift, not population averages
- **Catch pneumonia risk early** — weakened cough reflex + respiratory irregularity = danger

### For Clinicians
- **Objective, quantitative biomarkers** — no more "rate their facial expression on a scale of 1-5"
- **Continuous monitoring between visits** — not just a snapshot every 6 months
- **Multi-modal correlation** — when voice AND face AND heart all flag simultaneously, confidence skyrockets

### For Research
- **Longitudinal data collection** — every 2-second tick is logged with full feature traces
- **Per-patient baselines** — autoencoder learns YOUR normal, detects YOUR abnormal
- **Open architecture** — add new modalities (gait via accelerometer? handwriting via tablet?) without changing the core

---

## Demo

### Live Clinical Dashboard
The dashboard polls `/status` every second, showing all four modalities with color-coded risk badges:

- **Green (OK)** — within normal range
- **Orange (HIGH)** — elevated, monitor closely
- **Red (ALERT)** — multiple indicators flagged, immediate review

The combined PD risk score (0-100) drives the header pill, the large number display, and the gradient track with animated thumb.

### Voice + Cough (Gradio UI)
Real-time mic analysis at `http://127.0.0.1:7860`:
- **Live Demo tab** — speak into your mic, see SVM classification update every 2 seconds
- **Voice SVM** — probability of healthy vs. PD, with trend graph
- **Cough analysis** — cough into the mic, get instant PD likelihood scoring
- **Combined score** — voice (55%) + cough (45%) blended risk

### Face Expression Detection
The dashboard webcam runs **face-api.js** in-browser:
- Detects 7 expressions (neutral, happy, sad, angry, anxious, surprised, distressed)
- Posts expression + confidence to backend every 2 seconds
- Backend tracks rolling variance — low variance = **hypomimia** (a hallmark PD symptom)
- Face ring overlay turns orange on persistent flat affect

### Heart Monitoring (iPhone)
Point your iPhone at your face. The Presage SmartSpectra SDK extracts:
- Heart rate via remote photoplethysmography (rPPG)
- Breathing rate via respiratory analysis
- Stress score from HRV patterns
- Streamed to the dashboard in real-time via ngrok tunnel

---

## Technical Deep Dive

### Voice: Dual-Path Inference

**Path 1 — UCI SVM Classifier (supervised)**
- 5 clinical features extracted via Praat (parselmouth) + librosa:
  - HNR (Harmonics-to-Noise Ratio)
  - Spectral Flatness (10x separation between PD and healthy)
  - MFCC2 (vocal tract shape)
  - Voiced Fraction (speech continuity)
  - Energy CV (volume stability)
- RBF-SVM with `C=10`, `class_weight='balanced'`, Platt-calibrated probabilities
- Trained on UCI Parkinson's dataset (195 samples: 48 healthy, 147 PD)
- **5-fold CV accuracy: 98.3% +/- 1.6%**

**Path 2 — Personal Autoencoder (unsupervised, Vultr-hosted)**
- 5 librosa features: energy (dB), energy std, spectral centroid, spectral bandwidth, zero crossing rate
- Tiny autoencoder: `5 -> 4 -> 2 -> 4 -> 5` (46 parameters)
- Trained per-patient: learns YOUR voice, flags YOUR drift
- Anomaly score = MSE of reconstruction vs input
- Threshold = 90th percentile of training MSE
- Deployed on Vultr cloud instance at `140.82.11.174:8000`

### Cough: Rule-Based Feature Scoring

No labeled PD cough dataset exists publicly, so we built a rule-based system calibrated against clinical literature:

- **Hysteresis detection**: Two-threshold state machine on RMS envelope (avoids false positives from speech)
- **8 features per cough**: spectral centroid, ZCR, crest factor, phase power ratio, rise time, peak-to-decay ratio, expulsive duration, spectral slope
- **Weighted scoring**: Features mapped to [0,1] sub-scores with clinically-informed weights summing to 1.0
- **Validated**: Healthy coughs score 27-33%, PD-simulated coughs score 55-71%

### Heart: Presage rPPG + Risk Engine

- **Presage SmartSpectra SDK** on iPhone extracts vital signs from camera video via remote photoplethysmography
- Custom **AeyronBridge** (SwiftUI) streams data to FastAPI backend through ngrok HTTPS tunnel
- **Risk formula**: `vitals_risk = (hr_risk * 0.35) + (hrv_risk * 0.35) + (stress * 0.30)`
  - HR > 100 or < 55 bpm = high risk (cardiac dysautonomia)
  - HRV < 15 ms = high risk (autonomic dysfunction)
  - Stress > 0.6 = elevated (sympathetic overdrive)

### Face: Browser-Based Hypomimia Detection

- **face-api.js** (TinyFaceDetector + FaceExpressionNet) runs entirely in the browser
- Detects dominant facial expression + confidence every 2 seconds
- Backend maintains `FaceEmotionBuffer` — rolling window of 30 confidence values
- **Hypomimia flag**: triggered when variance < 0.04 or std < 0.20 (abnormally flat expression)
- Combined with voice data: monotone voice + flat face = strong PD indicator

### Combined Score: Dynamic Weight Renormalization

```python
weights = {"voice": 0.30, "heart": 0.25, "cough": 0.25, "face": 0.20}

# Only active modalities contribute
active_weights = {m: w for m, w in weights.items() if m has data}
total = sum(active_weights.values())
combined = sum(w * score / total for m, (w, score) in active)
```

If only voice + cough are active, voice gets 55% and cough gets 45%. Add heart and face, all four contribute at their natural weights. The system never requires all modalities — it works with whatever you have.

---

## Project Structure

```
Aeyron/
  hypophonia/                  Voice analysis (Vultr autoencoder + SVM)
    aegis_telemetry/
      patient_client/          Gradio UI + feature extraction + live demo
        core/                  Acoustic features, config, mic buffer, network
          models/              Trained SVM + scaler (joblib)
      vultr_ml_server/         FastAPI on Vultr (autoencoder training + inference)
      parkinsons.data          UCI Parkinson's dataset (195 rows)

  cough/                       Cough acoustic analysis
    detect.py                  Hysteresis cough detection
    features.py                8-feature extraction
    pd_classifier.py           Weighted PD likelihood scoring
    audio/                     Test audio (healthy + PD-simulated)
    baselines/                 Per-patient baseline features

  heart/                       Presage SDK cardiac monitoring
    README.md                  Architecture + demo setup

  backend/                     Unified FastAPI backend
    main.py                    /vitals /voice /cough /status endpoints
    face_emotion.py            Rolling variance hypomimia detection
    demo.html                  Live clinical dashboard (canvas charts + face-api.js)
    presage_simulator.py       3-scenario simulator for demo

  SmartSpectra/                Presage SmartSpectra SDK (iOS/Android/C++)
    swift/samples/demo-app/    Custom AEYRON Sentinel iOS app
```

---

## Setup & Run

### Quick Start (Voice + Cough + Face)

```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Dashboard
cd backend
python3 -m http.server 9080
# Open http://localhost:9080/demo.html
# Webcam face detection starts automatically

# Terminal 3: Voice + Cough (Gradio)
cd hypophonia/aegis_telemetry/patient_client
pip install -r requirements.txt
python3 main_ui.py
# Open http://127.0.0.1:7860 → Live Demo tab → Start
```

### Full Setup (All 4 Modalities)

```bash
# Steps 1-3 above, plus:

# Terminal 4: ngrok tunnel for iPhone
ngrok http 8000

# Xcode: Open SmartSpectra/swift/samples/demo-app/demo-app.xcodeproj
# Update ngrok URL in ContentView.swift
# Build and deploy to iPhone
# Point iPhone camera at face → vitals stream to dashboard
```

### Vultr Autoencoder Setup

```bash
# Enroll UCI baselines (one-time)
cd hypophonia/aegis_telemetry/patient_client
python3 train_uci_baseline.py              # healthy cohort → "uci"
python3 train_uci_baseline.py --status 1   # PD cohort → "uci_pd"
python3 train_baseline.py                  # personal voice → "default"
```

---

## Tools, Libraries & Hardware

### Software

| Category | Technology |
|---|---|
| **Voice features** | librosa (spectral analysis), parselmouth/Praat (clinical voice metrics) |
| **Voice ML** | scikit-learn (RBF-SVM, 98.3% accuracy), PyTorch (autoencoder) |
| **Cough analysis** | scipy (signal processing, Butterworth filters), librosa (features) |
| **Cardiac sensing** | Presage SmartSpectra SDK (rPPG, vital signs extraction) |
| **Face detection** | face-api.js (TinyFaceDetector + FaceExpressionNet, in-browser) |
| **Backend** | FastAPI, uvicorn, httpx, pydantic |
| **Cloud ML** | Vultr cloud instance (Ubuntu, PyTorch autoencoder server) |
| **Voice UI** | Gradio (real-time web interface) |
| **Dashboard** | Vanilla HTML/CSS/JS, Canvas API (no charting library) |
| **iOS app** | SwiftUI, Presage SmartSpectra Swift SDK |
| **Audio capture** | sounddevice (Python, 16 kHz mono) |
| **Tunnel** | ngrok (iPhone to localhost HTTPS) |
| **Dataset** | UCI Parkinson's Disease dataset (195 samples) |

### Hardware

| Device | Purpose |
|---|---|
| **Laptop microphone** | Voice + cough audio capture |
| **iPhone 15+** | Presage SmartSpectra rPPG (heart rate, breathing rate via camera) |
| **Laptop webcam** | face-api.js facial expression detection (hypomimia) |
| **Vultr cloud VM** | Per-patient autoencoder training + inference |

---

## Sponsor Categories

### MLH Best Use of Vultr
Our **Vultr-hosted autoencoder server** provides per-patient voice anomaly detection. Each patient enrolls their personal voice baseline; the autoencoder learns their normal speech patterns and flags drift over time — catching gradual degradation that population-level classifiers miss. The server runs on a Vultr Ubuntu instance with FastAPI, handling enrollment, inference, and longitudinal history via REST API.

### MLH Best Use of Presage
The **Presage SmartSpectra SDK** is the backbone of our cardiac/respiratory modality. It extracts clinical-grade heart rate, HRV, breathing rate, and stress metrics from nothing but an iPhone selfie camera — no wearables, no contact sensors. We built a custom iOS app (AeyronBridge) that streams Presage vitals through ngrok to our backend, where they're fused with voice, cough, and face data into a unified PD risk score.

---

## What Makes This Different

1. **Truly contactless** — no wearables, no special sensors. A phone and a mic are all you need.
2. **Multi-modal fusion** — four independent biomarker streams reinforce each other. When voice AND face AND heart all flag, it's not a coincidence.
3. **Personal baselines** — the autoencoder doesn't compare you to a population average. It learns YOUR voice and flags YOUR changes.
4. **Graceful degradation** — works with 1 modality, better with 2, best with all 4. Dynamic weight renormalization means nothing breaks if a sensor is unavailable.
5. **Real-time** — 2-second inference ticks, 1-second dashboard updates. Not a "submit and wait" system.
6. **Clinically grounded** — every feature, threshold, and weight is based on published PD research. We didn't just throw data at a neural network.
7. **98.3% voice classification accuracy** — on real UCI Parkinson's data, not synthetic benchmarks.

---

## Hackathon Compliance

- All code written from scratch during the hackathon event period
- No pre-existing code reused; concept existed beforehand but all implementation is original
- External dependencies are standard open-source libraries
- Presage SmartSpectra SDK used as provided — no modification to SDK source
- Clinical knowledge from published research — all algorithms and scoring built from scratch
- Repository is public

---

## Team

Built at Hack Canada 2025.

---

*Aeyron Sentinel — four modalities, one score, zero wearables. Parkinson's detection that fits in your pocket.*
