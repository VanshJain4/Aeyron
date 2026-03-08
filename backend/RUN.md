# Run AEYRON Sentinel — single runbook

One flow: backend, then either **SDK (primary, accurate)** or **Python bridge (fallback, estimates)**. Then open the dashboard.

## Step 0: API key (for SDK path)

- Get a Presage API key from [physiology.presagetech.com](https://physiology.presagetech.com).
- Set it in one of:
  - **.env** in the repo root: `PRESAGE_API_KEY=your_key`
  - **Swift app**: in `SmartSpectra/swift/samples/demo-app/ContentView.swift`, replace `"YOUR_API_KEY_HERE"` (or the existing key) with your key.  
  The backend does not use the key; only the Presage SDK (Swift app) needs it.

## Step 1: Start the backend

```bash
cd /Users/pingashvohra/Aeyron/backend
./stop_all.sh
./run_live_demo.sh
```

Leave this terminal open. You should see:

- `Starting API on http://localhost:8000 ...`
- `Serving demo page on http://localhost:9080 ...`
- Instructions for a second step (SDK or bridge).

## Step 2 (primary): Run the Presage SDK for accurate vitals

This is the path for **accurate** heart rate and breathing. API key is required.

**First time with Xcode?** → See **[XCODE_FIRST_TIME.md](XCODE_FIRST_TIME.md)** for step‑by‑step (open project, pick iPhone, set API key, Run, then use the app).

1. Open **Xcode**: open `SmartSpectra/swift/samples/demo-app.xcodeproj` (from the repo root).
2. Set run destination to **iPhone simulator** or **physical iPhone** (not “My Mac” — the Presage framework has no macOS slice).
3. Set your API key in `ContentView.swift` (replace the placeholder or existing key).
4. Build and run the app (**▶** or Cmd+R).
5. In the app:
   - Scroll to **AEYRON Sentinel**.
   - Turn **ON** “Send vitals to AEYRON backend”.
   - Set **Backend URL** to `http://localhost:8000` (Mac) or `http://<your-computer-ip>:8000` (iOS on device).
6. Start a measurement (face the camera). The app will POST vitals from the **SmartSpectra SDK** to the backend. The dashboard will show **Live (SDK) — accurate**.

## Step 2 (fallback): Python bridge — estimates only

If you are not using Xcode, use the Python bridge. Numbers are **rough estimates**; for accurate vitals use the SDK.

In a **second terminal** (with Step 1 still running):

```bash
cd /Users/pingashvohra/Aeyron/backend
python3 -u live_vitals_bridge.py --interval 1
```

Leave it open. You should see `Bridge: camera opened.` and `Bridge: POST ok ...` every second. The dashboard will show **Live (camera estimate)**.

## Step 3: Open the dashboard

In your browser, open:

**http://localhost:9080/demo.html**

You should see:

- **Backend status** and **data source** (Live SDK / Live camera estimate / No data).
- **Primary vitals**: Heart rate, Breathing rate.
- **Secondary**: HRV, Stress, Face emotion, Vitals risk.

If the source is **SDK**, values are from Presage SmartSpectra. If the source is **bridge**, values are estimates and the dashboard labels them as such.

## Summary

| Step | Action |
|------|--------|
| 0 | Get API key from physiology.presagetech.com; set in .env or Swift app. |
| 1 | `./run_live_demo.sh` in backend (API + demo server). |
| 2a (primary) | Run Swift app in Xcode, enable AEYRON Sentinel, start measurement. |
| 2b (fallback) | In second terminal: `python3 -u live_vitals_bridge.py --interval 1`. |
| 3 | Open http://localhost:9080/demo.html. |
