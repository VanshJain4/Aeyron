# Get "Live (SDK)" on dashboard — exact steps

Use this when the dashboard shows **"Backend connected. Data: none"** and you want it to show **"Data: Live (SDK) — accurate"** with numbers.

---

## Step 1: Backend running (you have this ✓)

- Terminal: `cd /Users/pingashvohra/Aeyron/backend` then `./run_live_demo.sh`
- Leave it open. You should see API on 8000, demo on 9080.
- Dashboard at http://localhost:9080/demo.html shows "Backend connected" → good.

---

## Step 2: Swift app — settings

- Open **demo-app** in Xcode (from Aeyron or Documents).
- Run on **iPhone Simulator** (e.g. iPhone 17 Pro) — not "My Mac".
- In the app, on the **Checkup** tab:
  - **AEYRON Sentinel** section at top:
    - Turn **ON** "Send vitals to AEYRON backend".
    - Set **Backend URL** to: `http://localhost:8000` (simulator) or `http://<your-mac-ip>:8000` (physical device).

---

## Step 3: Record button enabled?

The **Record** button is enabled only when the Presage SDK reports **status OK** (face/chest in frame, good lighting, valid API key). If the button stays **disabled** (gray):

| Cause | What to do |
|-------|------------|
| **iPhone Simulator** | Simulator often has no real camera or poor feed, so the SDK never gets "OK". **Use a physical iPhone** (connect via cable, select it as run destination in Xcode, run the app there). |
| **API key missing or invalid** | In `ContentView.swift` set `apiKey` to your Presage key (from physiology.presagetech.com). Clean build (⇧⌘K) and run again. |
| **Wait a few seconds** | After the Checkup screen loads, the SDK needs a moment to start the camera and analyze the first frames. Keep your **face and upper chest** in frame and wait 5–10 seconds; the button may turn from gray to red (enabled). |
| **Lighting / framing** | Avoid very dark or very bright scenes. One face, centered; some chest visible. The SDK may show a toast hint (e.g. "No face found", "Face not centered") — follow it. |

Once the button is **red** and tappable, tap **Record** and continue to Step 4.

---

## Step 4: Start a measurement (required)

- In the app, **tap the red Record button** (or the control that starts the camera measurement).
- **Keep your face (and some chest) in frame** for at least 15–30 seconds so the SDK can compute heart rate and breathing.
- The app sends vitals to the backend **only when a measurement is running** and the SDK is producing data. If you never tap Record, the dashboard will stay "Data: none".

---

## Step 5: Check the dashboard

- In the browser, open or refresh: **http://localhost:9080/demo.html**
- Within a few seconds you should see:
  - **"Data: Live (SDK) — accurate"** (green)
  - Heart rate, breathing rate, vitals risk, etc. updating.

---

## If it still shows "Data: none"

| Check | Action |
|-------|--------|
| Did you tap **Record** and keep face in frame? | Start a measurement and wait 20–30 s. |
| Backend URL in app | Must be `http://localhost:8000` for simulator (no typo, no trailing slash is OK). |
| Using physical iPhone? | Use your Mac’s IP in Backend URL; phone and Mac on same Wi‑Fi. |
| Backend really on 8000? | In terminal where you ran `./run_live_demo.sh`, confirm it says port 8000. |
| App build | In Xcode: Product → Clean Build Folder (⇧⌘K), then Run (⌘R). |

---

## One-line checklist

Backend running → App on **device or simulator** → "Send vitals" ON → Backend URL set → **Record button enabled (red)** → Tap Record, face+chest in frame 20–30 s → Refresh demo.html → "Live (SDK)".
