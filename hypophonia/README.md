# Aegis Hypophonia — Edge-to-GPU Neurological Voice Telemetry
> Targeting: [MLH] Best Use of Vultr
---

## What This Is

Aegis Hypophonia is a real-time voice analysis system that detects early vocal biomarkers associated with Parkinson's disease — specifically **hypophonia** (reduced vocal loudness and range) and other speech-quality degradations. The system captures microphone audio, extracts clinically-relevant acoustic features, and runs dual-path machine learning inference: one path sends features to a **Vultr-hosted GPU/compute server** for personalized anomaly detection via a trained neural autoencoder, and a second path runs an on-device SVM classifier trained on real PD and healthy voice data.

The entire live inference loop runs in under 2 seconds per tick with no upload delay — because the heavy ML is co-located with the data on Vultr.

---

## Why Vultr

Vultr is the backbone of this project's cloud ML layer. The FastAPI inference server runs on a Vultr instance at `140.82.11.174:8000`. Here is exactly what Vultr enables:

1. **One-click deployment** — the server was live in minutes. `uvicorn server:app --host 0.0.0.0 --port 8000` behind `ufw allow 8000/tcp` is all it took. No managed-service overhead, no cold starts.
2. **Always-on persistent storage** — patient models (`.pt` weights + `.json` metadata) are written to disk on the Vultr instance and survive across inference requests. The server loads each patient's trained autoencoder on every `/api/infer` call — this is only viable because Vultr gives you a real persistent compute instance.
3. **Scalable compute for per-patient training** — every time a patient enrolls, the server trains a fresh PyTorch autoencoder (150 epochs, Adam optimizer) on their personal voice baseline in real time. Without Vultr compute this would be client-side or not at all.
4. **GPU-ready** — the server code uses `torch.device("cuda" if torch.cuda.is_available() else "cpu")`. Scaling to a Vultr Cloud GPU instance requires zero code change.
5. **Real endpoint for a real demo** — the Gradio UI, the live tick loop, and the doctor dashboard all hit the same live Vultr URL. This is not a mock.

---

## System Architecture

```
Microphone (16 kHz mono)
        |
        v
  LiveMicBuffer (20 s ring buffer, background thread)
        |
        v
  Every 2 seconds: get last 10 s of audio
        |
        +-------- PATH 1: Personal Baseline (Vultr) ---------+
        |                                                      |
  Split into two 5 s chunks                                   |
  Extract librosa features (quick_test.py)                    |
  Average the two 5-dim vectors                               |
  POST /api/infer  →  Vultr FastAPI server                    |
  Autoencoder reconstructs → MSE anomaly score               |
  Compare to trained threshold → normal / flagged            |
        |                                                      |
        +-------- PATH 2: SVM Classifier (local) ------------+
        |
  Use same 10 s audio
  Extract acoustic features via Praat + librosa (acoustic_features.py)
  Build 5-dim UCI-style vector [HNR, SpectralFlatness, MFCC2, VoicedFraction, EnergyCv]
  Run local RBF-SVM (core/models/local_svm.joblib) → P(healthy), P(PD)
        |
        v
  Gradio UI (live_demo.py) renders combined result every 2 s
```

---

## Vultr Server: What It Does

**Endpoint base:** `http://140.82.11.174:8000`

### POST /api/enroll

Trains a new patient-specific autoencoder from scratch.

- Input: `patient_id` (string) + `baseline_data` (N x 5 float matrix, minimum 10 rows)
- Fits a MinMax scaler across baseline rows (per-feature min/max)
- Scales baseline to [0, 1]^5
- Trains `Autoencoder` (PyTorch, 150 epochs, Adam lr=0.01, MSE loss)
- Threshold = 90th percentile of per-sample reconstruction MSE on training data
- Saves `{patient_id}.pt` (weights) + `{patient_id}_meta.json` (min, max, threshold, baseline_loss)
- Returns: `{"status": "Model trained successfully", "baseline_loss": ..., "threshold": ...}`

### POST /api/infer

Runs anomaly detection for a patient.

- Input: `patient_id` + `current_data` (5 floats)
- Loads saved scaler meta + model weights
- Scales input using saved min/max, clips to [0, 1]
- Forward pass through autoencoder → MSE(reconstruction, input)
- Returns: `anomaly_score`, `status` (normal/flagged), `threshold`, `features_sent`

### GET /api/profile/{patient_id}

Returns training metadata: threshold, baseline_loss, scaler min/max per feature. Used by the doctor dashboard and profile view.

### GET /api/history/{patient_id}

Returns in-memory list of all inference calls this session (anomaly_score + status per tick). Used by doctor dashboard to plot trend.

### Autoencoder Architecture

```
Input (5) → Linear(5→4) → ReLU → Linear(4→2) → ReLU   [Encoder: bottleneck dim=2]
          → Linear(2→4) → ReLU → Linear(4→5) → Sigmoid [Decoder]
Loss: MSE(reconstruction, scaled_input)
```

The bottleneck forces the model to learn a 2-dimensional compressed representation of a healthy voice. At inference, any voice that does not reconstruct well (high MSE) is anomalous — which is the patient's voice drifting from their enrolled baseline.

### Why Per-Patient Models

Parkinson's vocal symptoms are highly individual. A patient's baseline energy, spectral profile, and pitch variation are determined by their anatomy, age, gender, and speaking style — not just disease state. By training one autoencoder per patient ID on their own voice recordings, the threshold is calibrated to *their* normal. Deviation from their personal normal is what matters, not deviation from a population mean.

Three patient IDs are enrolled on the Vultr server:

| patient_id | Trained on | Purpose |
|---|---|---|
| `default` | Patient's own voice (WhatsApp recordings) | Personal baseline anomaly detection |
| `uci` | UCI Parkinson's Dataset healthy cohort (48 subjects) | Population healthy reference |
| `uci_pd` | UCI Parkinson's Dataset PD cohort (147 subjects) | Population PD reference |

---

## Feature Extraction Pipeline

### Path 1: Personal Baseline Features (5-dim, librosa)

Extracted by `patient_client/core/quick_test.py`. Inspired by MARTA-style mel-spectrogram framing (400 ms frames, 65 mel bins, log-mel, 50% hop).

| Feature | Description | Hypophonia signal |
|---|---|---|
| `mean_energy_db` | Mean log-mel frame energy (dB) | Low in hypophonia (quiet voice) |
| `energy_std_db` | Std of log-mel frame energy | Low = flat/monotone prosody |
| `spectral_centroid_mean` | Mean spectral centroid (Hz) | Shifted in PD voices |
| `spectral_bandwidth_mean` | Mean spectral bandwidth | Changes with vocal quality |
| `zero_crossing_mean` | Mean zero-crossing rate | Higher in noisy/breathy voices |

**Extraction:**
1. 16 kHz mono audio → mel spectrogram (N_FFT=512, N_MELS=65, hop=256, win=512)
2. Power to dB (log-mel), reference = max value (relative dB)
3. Per-frame energy = mean over mel bins
4. Spectral centroid, bandwidth, ZCR via librosa on raw samples
5. Two 5 s chunks are each extracted → averaged → single 5-dim vector sent to Vultr

### Path 2: UCI-Style Acoustic Features (5-dim, Praat + librosa)

Extracted by `patient_client/core/acoustic_features.py`. These five features were chosen specifically for robustness on any audio — including phone-speaker-to-microphone playback, compressed audio, and room acoustics. Jitter and shimmer (traditional PD biomarkers) were removed because Praat's PointProcess algorithm fails to produce non-zero values on audio that has gone through a speaker-mic chain, making them uninformative.

| Feature | Tool | PD signal |
|---|---|---|
| `HNR` (dB) | Praat harmonicity, 75th percentile of voiced frames | Lower in PD (noisier voice) |
| `SpectralFlatness` | librosa mean flatness | ~10x higher in PD (0.15-0.28 vs 0.016-0.020 healthy) |
| `MFCC2` | librosa 2nd MFCC mean | Spectral tilt, gender-neutral discriminator |
| `VoicedFraction` | librosa pyin voiced frame fraction | Lower in PD (more unvoiced pauses) |
| `EnergyCv` | RMS energy coefficient of variation | Higher in PD (tremor-induced energy fluctuations) |

**Why the 75th percentile for HNR:** The mean HNR is dragged down by room noise and silence frames. The 75th percentile captures the clearest voiced frames, matching clinical UCI recordings where patients sustained a clean sustained vowel. This makes the live-mic HNR comparable to the UCI training distribution.

**Audio segmentation:** The 10 s audio buffer is split as:
- First 5 s → Task A (sustained vowel / any speech) → Praat harmonicity + HNR
- Next 5 s → Task B (continuous speech) → pitch std, RMS mean
- Full 10 s combined → librosa features (SpectralFlatness, MFCC2, VoicedFraction, EnergyCv)

---

## Local SVM Classifier

Because the Vultr autoencoder's UCI comparison uses reconstruction MSE (unsupervised), the confidence for borderline cases can be ambiguous. To get a direct, confident PD vs healthy classification, a supervised SVM classifier was trained locally on real audio features.

### Training Data

| Source | Class | Count |
|---|---|---|
| `Parkinson-Patient-Speech-Dataset/denoised-speech-dataset` (real PD patient recordings) | PD | 205 vectors |
| `core/data/` (patient's own voice recordings, WhatsApp audio) | Healthy | 36 vectors |

Each vector was produced by running the exact same `extract_features()` + `uci_features_to_vector()` pipeline on real audio files, ensuring training and inference use identical feature distributions.

### Model

```python
SVC(kernel='rbf', C=10, probability=True, class_weight='balanced')
```

- `class_weight='balanced'` handles the 205:36 class imbalance
- `probability=True` enables `predict_proba()` for confidence scores
- Feature scaling: `MinMaxScaler(feature_range=(-1, 1))` — saved as `local_scaler.joblib`
- **5-fold cross-validation accuracy: 98.3% ± 1.6%**
- Saved as: `core/models/local_svm.joblib` and `core/models/local_scaler.joblib`

### Inference Results (Confirmed Live)

| Audio source | P(healthy) | P(PD) | Result |
|---|---|---|---|
| PD patient recording played through Mac speakers | 2-7% | 93-98% | PD |
| User speaking directly into Mac microphone | 93-98% | 2-7% | Healthy |

The key discriminating feature is **SpectralFlatness**: PD voices show 0.15–0.28, healthy voices show 0.016–0.020. This is a ~10x separation, making it the strongest single feature. Combined with HNR, VoicedFraction, and EnergyCv, the SVM boundary is clean.

---

## Live Demo

The live demo runs as a Gradio web UI. It uses a background audio capture thread that continuously fills a 20-second ring buffer from the system microphone at 16 kHz mono. Every 2 seconds, inference runs on the last 10 seconds.

### Running It

```bash
cd aegis_telemetry/patient_client
pip install -r requirements.txt
python3 main_ui.py
```

Opens at `http://127.0.0.1:7860`.

### Demo Protocol

To demonstrate detection:

1. **PD detection:** Play a PD voice recording (e.g. any file from the Parkinson-Patient-Speech-Dataset) through Mac speakers at normal volume, 20-30 cm from mic. After 10 seconds of audio, the live display shows PD probability 93-98%.
2. **Healthy detection:** Click Stop, then Start again. Speak directly into the microphone for 10+ seconds. The display shows healthy probability 93-98%.

**Important:** When playing audio through AirPods, the AirPods microphone picks up room ambient noise, not the audio playing in the ears. Use the Mac built-in microphone with audio playing through Mac speakers or wired headphones.

### What the Live UI Shows

Every 2 seconds the display updates with:

```
## LIVE — Voice Analysis

### Voice features (last 10 s)
| HNR (dB)          | 12.4500 |
| Spectral Flatness  | 0.0180  |
| MFCC2              | -8.2300 |
| Voiced Fraction    | 0.7200  |
| Energy CV          | 0.4100  |

### SVM Classification (98% accuracy)
| Result             | HEALTHY |
| Healthy probability | 96.2%  |
| PD probability     | 3.8%   |

---

### Personal baseline (librosa)
| mean_energy_db     | -22.4000 |
| ...                | ...      |
| MSE                | 0.034512 |
| Threshold          | 0.071000 |
| Ratio              | 0.486    |
| Result             | normal   |
| Risk %             | 0%       |
```

---

## Datasets Used

### UCI Parkinson's Dataset
- **Source:** UCI Machine Learning Repository — "Parkinson's Disease Classification" by Max Little et al.
- **Content:** 195 biomedical voice measurements from 31 subjects (23 PD, 8 healthy). Features include fundamental frequency, jitter, shimmer, HNR, RPDE, DFA, PPE.
- **Usage:** The 48 healthy-subject rows were used to enroll the `uci` patient baseline on Vultr. The 147 PD rows enrolled `uci_pd`. This gives the Vultr autoencoder a population-level healthy vs PD reference.
- **File:** `aegis_telemetry/parkinsons.data`

### Parkinson Patient Speech Dataset (Denoised)
- **Source:** Kaggle — "Parkinson Patient Speech Dataset" (denoised version)
- **Content:** Audio recordings of PD patients performing sustained vowel and speech tasks
- **Usage:** 205 audio files were processed through `acoustic_features.py` to extract [HNR, SpectralFlatness, MFCC2, VoicedFraction, EnergyCv] vectors, which form the PD training class for the local SVM classifier
- **Location used from:** `/Parkinson-Patient-Speech-Dataset/denoised-speech-dataset/`

### Personal Voice Baseline (Healthy)
- **Source:** Voice recordings captured as WhatsApp audio messages
- **Content:** 4 recordings of the patient (healthy adult) speaking naturally
- **Usage:** Used as the healthy training class for the local SVM (36 vectors extracted), and as the `default` patient enrollment on Vultr for personal anomaly detection
- **Location:** `patient_client/core/data/`

---

## Enrollment (Baseline Training)

To re-enroll baselines on Vultr (if the server restarts or weights are lost):

```bash
cd aegis_telemetry/patient_client

# Enroll personal baseline (default patient)
python3 enroll_live_baselines.py

# Enroll UCI healthy + PD baselines
python3 train_uci_baseline.py
```

`enroll_live_baselines.py` reads all `.wav` files from `core/data/`, extracts features, and sends to `POST /api/enroll` with `patient_id="default"`. At enrollment the server reported:
- Personal baseline loss: 0.0224
- Healthy UCI baseline loss: 0.0344

---

## Doctor Dashboard

A static HTML dashboard at `aegis_telemetry/doctor_dashboard/index.html` plots the patient's anomaly score history over time by polling `GET /api/history/{patient_id}` on the Vultr server. Open it directly in a browser — no server needed on the client side. The Vultr URL and patient ID are pre-filled.

---

## Repo Structure

```
hypophonia/
  aegis_telemetry/
    vultr_ml_server/
      server.py                  # FastAPI app (runs on Vultr)
      models/
        autoencoder.py           # PyTorch autoencoder 5->4->2->4->5
      requirements.txt
      DEPLOY_VULTR.md            # Deployment instructions
    patient_client/
      main_ui.py                 # Gradio UI (15s record + live demo tabs)
      live_demo.py               # Live 2s tick inference loop
      train_baseline.py          # Enroll personal baseline to Vultr
      train_uci_baseline.py      # Enroll UCI healthy + PD to Vultr
      enroll_live_baselines.py   # Quick re-enrollment from core/data/
      demo_compare.py            # Standalone demo comparison script
      core/
        config.py                # Vultr URL, patient IDs
        quick_test.py            # Librosa personal features (5-dim)
        acoustic_features.py     # Praat + librosa UCI features (5-dim)
        live_buffer.py           # Thread-safe mic ring buffer
        client_network.py        # HTTP client for Vultr API
        capture.py               # sounddevice mic capture
        data/                    # Healthy baseline audio (WAVs)
        models/
          local_svm.joblib        # Trained SVM classifier (98.3% CV)
          local_scaler.joblib     # MinMaxScaler for SVM features
          uci_svm_classifier.joblib  # UCI feature SVM (22-dim)
          uci_scaler.joblib
      live_demo_profile.csv      # Profiling trace of every live tick
    doctor_dashboard/
      index.html                 # Dashboard (polls Vultr history API)
      app.js
    parkinsons.data              # UCI Parkinson's CSV
    PIPELINE.md                  # Technical pipeline notes
    README.md                    # Vultr award README (this file's parent)
```

---

## Dependencies

### Vultr Server (Python 3.10+)

```
fastapi
uvicorn
torch          # CPU-only install: --index-url https://download.pytorch.org/whl/cpu
numpy
pydantic
```

### Patient Client (Python 3.11+)

```
gradio
librosa
numpy
sounddevice
parselmouth        # Python bindings for Praat
scikit-learn
joblib
requests
```

---

## Technical Q&A

**Q: How does the autoencoder know what "normal" sounds like?**

A: During enrollment, the patient records several minutes of their own voice. These are chunked into 5-second segments, each producing a 5-dim feature vector. The autoencoder is trained (on Vultr) to reconstruct these vectors with minimal MSE. The threshold is the 90th percentile of reconstruction errors on the training set. At inference, a new voice recording produces a new feature vector — if the autoencoder cannot reconstruct it well (MSE above threshold), the voice has changed from baseline.

**Q: Why not just use the UCI dataset directly for inference instead of training a new model per patient?**

A: The UCI dataset gives population-level healthy vs PD separation, but PD is diagnosed over years — vocal characteristics change gradually and individually. The personal autoencoder detects *longitudinal drift* in a single person's voice. Both signals are surfaced in the UI: the SVM gives "does this voice pattern look like PD clinically?" and the autoencoder gives "has this patient's voice changed from their own baseline?"

**Q: Why 5 features?**

A: The Vultr server's autoencoder has `INPUT_DIM=5` hard-coded (the architecture is `5→4→2→4→5`). Five features is a deliberate constraint: it forces the model to learn the most informative dimensions rather than memorizing noise, and it keeps inference latency sub-millisecond on the Vultr server. The five UCI features were chosen for discriminability (SpectralFlatness has ~10x PD/healthy separation) and robustness to audio recording conditions (unlike Jitter/Shimmer which fail on phone-speaker audio).

**Q: Why does Jitter/Shimmer fail on phone audio?**

A: Jitter measures cycle-to-cycle variation in fundamental frequency period. Praat's PointProcess algorithm (used to detect glottal pulses) requires clean, close-mic recordings like clinical sustained vowels. When audio plays through a phone speaker into a room microphone, acoustic reflections, resampling, and compression artifacts cause the algorithm to fail to detect any glottal pulses — returning jitter=0 and shimmer=0 for every frame. Two different audio signals both producing [0, 0, HNR, ...] vectors are indistinguishable to the classifier. The librosa-based features (SpectralFlatness, MFCC2, VoicedFraction, EnergyCv) compute on any audio without glottal pulse detection.

**Q: What is the risk % shown in the UI?**

A: Risk % is derived from the personal autoencoder's MSE/threshold ratio:
- Ratio < 0.5 → 0% (well within normal)
- Ratio = 1.0 → 50% (exactly at threshold)
- Ratio >= 1.5 → 100% (clearly flagged)
- Linear interpolation between 0.5 and 1.5

This is separate from the SVM probability — it measures how far the current voice has drifted from the patient's own trained baseline, not whether the voice pattern resembles clinical PD.

**Q: How is the SVM probability computed?**

A: `SVC(kernel='rbf', C=10, probability=True)` uses Platt scaling internally — after training, the SVM's decision function scores are calibrated to probabilities using logistic regression on cross-validated predictions. `predict_proba()` returns `[P(healthy), P(PD)]`. The output is the direct probability from this calibrated model.

**Q: What is the bottleneck dimension of the autoencoder and why?**

A: The bottleneck is 2 dimensions (the encoder outputs a 2-dim latent vector `z`). With 5 input features, a 2-dim bottleneck forces the model to find the two most important axes of variation in the patient's healthy voice. This also prevents the trivial identity solution (a 5-dim bottleneck could just pass through the input unchanged). MSE reconstruction quality on new data is a direct measure of whether the voice lies on the learned 2D manifold.

**Q: Why not use a larger neural network or transformer?**

A: The 5-dim input doesn't warrant it. A 5→4→2→4→5 autoencoder has 46 parameters. Adding more layers would overfit with small baseline datasets (10-50 recordings per patient) and add latency to Vultr inference. The SVM already handles the supervised PD/healthy discrimination with 98.3% accuracy — the autoencoder's job is only longitudinal anomaly detection.

**Q: How does the live buffer work?**

A: `LiveMicBuffer` is a thread-safe ring buffer backed by a NumPy float32 array. A background thread runs a `sounddevice.InputStream` at 16 kHz, writing 0.5-second chunks into the ring buffer via a callback. The main inference loop calls `get_last_seconds(10.0)` which reads the last 10 seconds from the circular buffer using index arithmetic (no copy until read). The buffer capacity is 20 seconds (320,000 float32 samples = 1.2 MB).

**Q: What happens if the Vultr server is down?**

A: The SVM classifier runs entirely locally and continues to work. The personal baseline Vultr path will return an HTTP error, which is caught and logged but does not crash the UI. The display will show SVM results without the personal MSE section.

**Q: Is this a medical device?**

A: No. This is a research and demonstration tool for a hackathon. All outputs include "Not a clinical diagnosis." labels. The system does not store any patient health data permanently (Vultr history is in-memory only). Nothing here should be used for actual medical decision-making.

---

## Vultr Deployment Steps (for reference)

```bash
# On a fresh Vultr Ubuntu instance:
git clone <repo>
cd hypophonia/aegis_telemetry/vultr_ml_server

# Install CPU-only PyTorch first (saves ~1.8 GB disk)
pip3 install torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
pip3 install -r requirements.txt

# Open firewall port
ufw allow 8000/tcp && ufw --force enable

# Start server
uvicorn server:app --host 0.0.0.0 --port 8000
```

The server is stateless except for saved weights in `saved_weights/`. Patient models persist on disk across restarts (model files are small — each `.pt` is ~2 KB for a 46-parameter network).

---

*Aegis Hypophonia — real-time neurological voice telemetry, edge to cloud.*
