# Xcode first time — run the Presage app (step by step)

You’ve never used Xcode before. Follow these steps in order.

---

## 1. Open the project in Xcode

- Open **Finder**.
- Go to: **Aeyron** → **SmartSpectra** → **swift** → **samples**.
- Double‑click **demo-app.xcodeproj** (the blue icon).
- Xcode opens and shows the project (file list on the left, code in the middle).

---

## 2. Pick “iPhone” (not “My Mac”)

The app only runs on **iPhone** (simulator or real phone), not on Mac.

- At the **top left** of Xcode you see something like: **demo-app** | **My Mac** (or a device name).
- Click that **device name** (e.g. “My Mac”).
- A menu opens. Under **iOS** or **Simulators**, choose an **iPhone**:
  - e.g. **iPhone 16** or **iPhone 15** (simulator),  
  - or your **physical iPhone** if it’s connected.
- Click somewhere else to close the menu. The top bar should now show **iPhone 16** (or whatever you chose).

---

## 3. Put your API key in the code

- In the **left sidebar**, open: **demo-app** (folder) → **ContentView.swift**.
- In the code, find the line with `apiKey` (around line 24). It might say `"YOUR_API_KEY_HERE"` or already have a key.
- Replace the value between the quotes with your key:  
  `"VyamOjHtwU6eSxEY2zsD93csKLXJdWFGrnEIEA17"`
- Save: **File → Save** (or **Cmd+S**).

---

## 4. Run the app

- Click the **Play (▶)** button at the **top left** of Xcode, or press **Cmd+R**.
- Xcode will **build** (compile) the app. The first time can take 1–2 minutes.
- When it finishes, the **iPhone Simulator** opens (or your phone launches the app).
- If it asks for **camera permission**, choose **OK** or **Allow**.

---

## 5. Use the app and send vitals to the backend

- In the app, **scroll down** until you see **“AEYRON Sentinel”**.
- Turn **ON** the switch **“Send vitals to AEYRON backend”**.
- In **Backend URL** type:
  - **Simulator:** `http://localhost:8000`
  - **Real iPhone:** `http://YOUR_MAC_IP:8000` (e.g. `http://192.168.1.5:8000`). Find your Mac’s IP in **System Settings → Network → Wi‑Fi → Details**.
- **Start a measurement** (the button that starts the camera / measurement). Face the camera and wait.
- The app will send heart rate and breathing to your backend.

---

## 6. See the data on the dashboard

- On your **Mac**, open a browser and go to: **http://localhost:9080/demo.html**
- You should see **“Live (SDK) — accurate”** and numbers updating.

---

## If something goes wrong

- **“No library for macOS”**  
  You left **My Mac** selected. Go back to step 2 and choose an **iPhone** simulator or device.

- **“Build failed”**  
  Make sure you selected an **iPhone** (not My Mac). If it still fails, copy the error from Xcode and we can fix it.

- **Simulator has no camera**  
  The simulator may not have a real camera. Use a **physical iPhone** (connect with cable, select it as run destination, then run again).

- **Backend not running**  
  In Terminal run: `cd /Users/pingashvohra/Aeyron/backend` then `./run_live_demo.sh`. Leave it running.
