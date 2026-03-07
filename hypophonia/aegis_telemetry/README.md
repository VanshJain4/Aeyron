# Aegis Hypophonia (voice-only)

Edge-to-cloud telemetry: 5 voice features → Vultr ML server (autoencoder anomaly detection).

## Run order

1. **Vultr ML server** (on Vultr or local):
   ```bash
   cd vultr_ml_server && pip install -r requirements.txt && uvicorn server:app --host 0.0.0.0 --port 8000
   ```

2. **Patient client** (Gradio UI):
   ```bash
   cd patient_client && pip install -r requirements.txt && python main_ui.py
   ```
   Set "Vultr ML server URL" to `http://<Vultr Tailscale IP>:8000` (or `http://127.0.0.1:8000` for local).

3. **Doctor dashboard**: open `doctor_dashboard/index.html` in a browser, or serve the folder (e.g. `python -m http.server 8080` from `doctor_dashboard`). Set API base URL and Patient ID, then "Load history".

## Flow

- Sessions 1–5: recordings stored locally; after 5th, baseline is sent to server (`POST /api/enroll`).
- Session 6+: current vector sent to server (`POST /api/infer`); anomaly score stored and shown. Flagged if MSE > 3× baseline.
