# Live demo (30-min setup)

## What you get

- **Live camera** in the dashboard (browser asks for camera permission).
- **Vitals updating every 1 second** (simulator POSTs to backend; panel polls every 1s).
- Looks and feels live for the demo.

## Live data (real pulse from webcam)

Uses your camera to estimate heart rate (rPPG-style) and POSTs to the API. No simulator.

```bash
cd backend
pip install -r requirements.txt   # includes opencv-python-headless, numpy
chmod +x run_live_demo.sh
./run_live_demo.sh
```

Then open **http://localhost:9080/demo.html**. Face the camera; heart rate updates from the webcam. HRV, stress, breathing are placeholders; pulse is real.

---

## Simulated data: all-in-one local demo (no Next.js)

From the repo root:

```bash
cd backend
chmod +x run_local_demo.sh
./run_local_demo.sh
```

Then open in your browser: **http://localhost:9080/demo.html**

- Click **“Start camera”** and allow when the browser asks.
- Vitals will appear and update every second.

Ctrl+C in the terminal stops the API, simulator, and the demo server.

---

## Alternative: backend + simulator only (use with Next.js)

```bash
cd /Users/pingashvohra/Aeyron/backend
chmod +x run_demo.sh
./run_demo.sh
```

Or by hand:

**Terminal 1 – API**
```bash
cd /Users/pingashvohra/Aeyron/backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 – Simulator (1s interval for live feel)**
```bash
cd /Users/pingashvohra/Aeyron/backend
python3 presage_simulator.py B --interval 1
```

### 2. In your Next.js page

Import and render both:

```jsx
import LiveCameraView from "@/path/to/Aeyron/heart/LiveCameraView";
import VitalsPanel from "@/path/to/Aeyron/heart/VitalsPanel";

// In your page/layout:
<div>
  <LiveCameraView />   {/* Live camera feed */}
  <VitalsPanel />      {/* Vitals every 1s */}
</div>
```

VitalsPanel now polls every **1 second** (override with `NEXT_PUBLIC_VITALS_POLL_MS` if needed).

### 3. For the audience

- Allow **camera** when the browser asks → live feed.
- Vitals (HR, HRV, breathing, stress, face, risk) update every second from the simulator.
- For a **real** Presage pipeline later: run SmartSpectra C++/mobile app with camera and point it at this backend.

## Stop

- Simulator: Ctrl+C in its terminal.
- API: Ctrl+C in its terminal, or `kill -9 $(lsof -i :8000 -t)`.
