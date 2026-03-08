# Run the live demo (terminal + local hosting)

**Superseded by [RUN.md](RUN.md) for the full flow.** This file describes the Python-bridge-only steps.

**No Xcode needed.** Use the Python bridge (two terminals + browser). The Swift/SDK path is optional.

You need **two terminals**. The bridge must run in the foreground so the camera works (on macOS it often fails in the background).

## 1. First terminal — API + demo server

```bash
cd /Users/pingashvohra/Aeyron/backend
./stop_all.sh
./run_live_demo.sh
```

Leave this open. You should see:

- `Starting API on http://localhost:8000 ...`
- `Serving demo page on http://localhost:9080 ...`
- Instructions to open a **second terminal** for the bridge.

## 2. Second terminal — live vitals bridge (required)

With the first terminal still running:

```bash
cd /Users/pingashvohra/Aeyron/backend
python3 -u live_vitals_bridge.py --interval 1
```

Leave this open. You should see:

- `Bridge: camera opened.`
- `Bridge: POST ok heart=... breathing=...` every second.

If you see **“Could not open camera”**: close other apps using the camera and allow Terminal (or your IDE) in **System Settings → Privacy & Security → Camera**. Then run the command again.

---

## 3. Browser — open the demo

1. Open: **http://localhost:9080/demo.html**
2. Allow camera if the page asks.
3. Put your **face and upper chest** in frame.
4. Wait **~30 seconds** for heart rate and breathing to appear (the bridge needs a short buffer).
5. You should see “✓ LIVE FROM CAMERA” and numbers instead of “—”.

---

## 4. Stop everything

- In the **first** terminal (run_live_demo.sh): press **Ctrl+C** — stops API and demo server.
- In the **second** terminal (bridge): press **Ctrl+C** — stops the bridge.

---

## Quick checks

- **API:** http://localhost:8000 — should return JSON with `"message": "AEYRON Sentinel Vitals API"`.
- **Vitals:** http://localhost:8000/vitals — after the bridge has been POSTing, should show `"patient": "live"` and numeric `heart_rate` / `breathing_rate`.
- **Deps (once):** `python3 -m pip install -r requirements.txt` (from `backend/`).
