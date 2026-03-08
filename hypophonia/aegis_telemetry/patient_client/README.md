# Aegis patient client — live hypophonia check

- **Baseline (in code):** Put all baseline audio (e.g. .wav, .mp3) in `core/data/`. Then run:
  ```bash
  python3 train_baseline.py
  ```
  Every file in that folder is chunked and used; 5 vectors (evenly spread) are sent to Vultr.

- **Live:** Run the app, record 10 s, get analysis (Normal / Possible hypophonia).
  ```bash
  python3 main_ui.py
  ```

- **Dashboard:** Open `doctor_dashboard/index.html`; URL and patient ID are pre-filled. Load history to see anomaly scores over time.

Vultr URL is set in `core/config.py` (same for train, live, and dashboard).
