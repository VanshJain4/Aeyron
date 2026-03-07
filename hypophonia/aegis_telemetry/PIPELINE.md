# How the numbers are generated (full pipeline)

## 1. Feature extraction (client: `quick_test.py` + `main_ui.py`)

- **Input:** 5 s of audio (16 kHz mono).
- **Steps:**
  - Mel spectrogram: 512 FFT, 65 mel bins, 50% hop, log (dB).
  - **mean_energy_db:** mean of per-frame energy (dB).
  - **energy_std_db:** std of per-frame energy (prosody variation).
  - **spectral_centroid_mean:** mean spectral centroid (Hz).
  - **spectral_bandwidth_mean:** mean spectral bandwidth.
  - **zero_crossing_mean:** mean zero-crossing rate.
- **Output:** One 5-dim vector `[mean_energy_db, energy_std_db, spectral_centroid_mean, spectral_bandwidth_mean, zero_crossing_mean]`.

**Live:** 10 s is split into two 5 s chunks; we extract one vector per chunk and **average** the two vectors before sending (same chunk duration as baseline).

---

## 2. Baseline training (client `train_baseline.py` → server `POST /api/enroll`)

- All audio in `core/data/` → 5 s chunks → one 5-dim vector per chunk (same extraction as above).
- **Scaler:** `min_vals` and `max_vals` = min and max of each dimension over all baseline vectors.
- **Scale:** `scaled = (x - min) / (max - min)` so baseline lives in [0, 1]^5.
- **Model:** Autoencoder 5→4→2→4→5 (ReLU, Sigmoid on decoder). Trained to reconstruct scaled baseline (MSE loss, 150 epochs).
- **Threshold:** For each baseline vector we compute MSE(reconstruction, input). `threshold = max(per-sample MSE) × 1.2`.
- **Saved on Vultr:** `default.pt` (weights), `default_meta.json` (min, max, baseline_loss, threshold).

---

## 3. Inference (client `main_ui.py` → server `POST /api/infer`)

- Client sends the **single 5-dim vector** (averaged from two 5 s chunks).
- Server loads `default_meta.json` → gets min, max, threshold.
- **Scale:** `scaled = (current_data - min) / (max - min)`, then **clip to [0, 1]**.
- **Score:** Run autoencoder on scaled vector; `anomaly_score = MSE(reconstruction, scaled_input)`.
- **Status:** `normal` if score ≤ threshold, `flagged` (possible hypophonia) if score > threshold.

---

## 4. Why the same number shows

If you use the same mic, same distance, same voice, the two 5 s chunks give almost the same features every time → the averaged vector is almost identical → the same scaled input → the same MSE. So the score (e.g. 0.2010) is stable. That is expected.

---

## 5. Inspect what the model has

- **After a live check:** The UI shows "Features sent (raw)", "Threshold", and "Score (MSE)".
- **Profile (trained baseline):** `GET http://140.82.11.174:8000/api/profile/default` returns threshold, baseline_loss, scaler_min, scaler_max per feature (so you can see the range the model was trained on).
