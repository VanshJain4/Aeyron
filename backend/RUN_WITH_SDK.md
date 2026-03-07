# Run the demo with Presage SmartSpectra SDK

**See [RUN.md](RUN.md) for the single runbook.** This file keeps SDK-only details.

To use **Presage SmartSpectra SDK** for vitals (instead of the Python OpenCV bridge), use the Swift demo app and send its metrics to this backend.

## 1. Get a Presage API key

- Sign up at [physiology.presagetech.com](https://physiology.presagetech.com) and get an API key.
- The Swift app needs this key to run the SDK.

## 2. Start the AEYRON backend and demo page

In a terminal:

```bash
cd /Users/pingashvohra/Aeyron/backend
./stop_all.sh
./run_live_demo.sh
```

Leave it running. This starts the API (port 8000) and the demo page server (port 9080).

## 3. Run the SmartSpectra Swift demo app (with AEYRON bridge)

1. Open the Swift demo app in Xcode:
   - Open `SmartSpectra/swift/samples/demo-app.xcodeproj` (from the repo root).
2. In `ContentView.swift`, set your Presage API key:
   - Replace `"YOUR_API_KEY_HERE"` with your key from step 1.
3. Build and run the app on a **simulator or device** (Mac or iOS).
4. In the app, scroll to **"AEYRON Sentinel"**:
   - Turn **ON** “Send vitals to AEYRON backend”.
   - Set **Backend URL**:
     - **Mac app**: `http://localhost:8000`
     - **iOS device**: `http://<your-computer-ip>:8000` (e.g. `http://192.168.1.5:8000`). Your computer and phone must be on the same network.
5. Start a measurement in the app (face the camera). The app will POST vitals from the **SmartSpectra SDK** to your backend every time the metrics buffer updates.

## 4. Open the web demo

- In a browser, open **http://localhost:9080/demo.html** (or from another machine use `http://<computer-ip>:9080/demo.html`).
- You should see “✓ LIVE FROM CAMERA” and vitals coming from the **SDK** (via the Swift app), not the Python bridge.

## Summary

| Source              | What runs                          | Vitals from                    |
|---------------------|------------------------------------|--------------------------------|
| Python bridge       | `live_vitals_bridge.py` (Terminal 2)| OpenCV + FFT (no SDK)         |
| **SmartSpectra SDK**| Swift demo app (this flow)        | Presage SmartSpectra (rPPG, etc.) |

The backend API is the same: both the Python bridge and the Swift app POST to `POST /vitals` with the same JSON shape. The demo page only cares that `patient` is `"live"` and that heart/breathing rates are present.
