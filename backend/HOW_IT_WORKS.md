# How the live demo actually works

## The chain (what runs where)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  TERMINAL 2:  live_vitals_bridge.py                                      │
│  • Opens YOUR webcam (the one on your Mac).                              │
│  • Every frame: finds face + chest in the image.                         │
│  • Heart rate: tiny color changes on your face (green channel) → FFT     │
│    → needs ~50 samples (~3 sec) before it can show a number.              │
│  • Breathing: movement/brightness of chest area → FFT                   │
│    → needs ~80 samples (~5+ sec) before it can show a number.            │
│  • Every 1 second: POSTs { heart_rate, breathing_rate, patient: "live" }│
│    to http://localhost:8000/vitals                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  TERMINAL 1:  API (uvicorn) on port 8000                                 │
│  • Receives POST /vitals and stores the latest JSON in memory.           │
│  • GET /vitals returns that stored JSON (or empty if no POST ever came). │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  BROWSER:  http://localhost:9080/demo.html                               │
│  • Every 1 second: GET http://localhost:8000/vitals                      │
│  • If the JSON has patient: "live" and numbers → shows "✓ LIVE" + values│
│  • If the JSON is empty (all null) → "No data yet" + instructions        │
└─────────────────────────────────────────────────────────────────────────┘
```

Important: **The browser’s own camera is only for the “Start camera” preview.** The numbers come from the **bridge** (Terminal 2) using **its** camera. So you must run the bridge and have your face + chest in view of the **same machine’s camera** (the one the bridge is using).

## Why it might not work

| What you see | What it usually means |
|--------------|------------------------|
| "Backend: Not running" | Terminal 1 isn’t running or port 8000 is wrong. Start `./run_live_demo.sh`. |
| "Backend: Connected" but "No data yet" | API is up but **no POST** is reaching it. Either the bridge isn’t running (Terminal 2) or it’s failing (camera, or wrong port). |
| Bridge says "Could not open camera" | Another app is using the camera, or Terminal/app doesn’t have camera permission in System Settings → Privacy → Camera. |
| Bridge says "POST failed — is the API running on port 8000?" | Start Terminal 1 first (`./run_live_demo.sh`), then run the bridge in Terminal 2. |
| Bridge shows "POST ok" but heart/breathing are "measuring..." | Normal at first. Bridge needs ~3 sec of face for heart and ~5+ sec of chest for breathing. Keep face + upper chest in frame and wait. |
| Numbers look wrong or jump a lot | Algorithm is simple (rPPG + FFT). Lighting, motion, and distance affect it. It’s a demo, not medical-grade. |

## Why the numbers can be wrong

- **Heart rate** comes from small color changes on your face (green channel → FFT). It’s sensitive to lighting, head motion, and face position. Values can be 5–15 bpm off or jump.
- **Breathing rate** comes from chest-area motion/brightness. Same issues: movement and lighting make it noisy.
- **HRV and stress** in this demo are fixed placeholders (35 ms, 25%) — they are **not** measured from the camera.
- For **more accurate** camera-based vitals you’d use the Presage SmartSpectra SDK (Swift app path); the Python bridge is for a quick demo only.

## Quick check (is the bridge talking to the API?)

With Terminal 1 running, in another terminal:

```bash
curl -s http://localhost:8000/vitals
```

- If you see `"patient": "live"` and numbers → bridge is POSTing; refresh the demo page.
- If you see `"patient": null` and all nulls → no POST yet; run the bridge in Terminal 2 and wait until you see "Bridge: POST ok".
