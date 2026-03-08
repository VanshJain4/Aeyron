# Run AEYRON from this folder (full test)

**1. Stop everything elsewhere**
- Quit any bridge running from another folder (or close that terminal).
- In Xcode, stop the app if it’s running.

**2. Start the bridge from THIS folder**
```bash
cd "/Users/pingashvohra/Desktop/untitled folder 2/Aeyron"
./run_aeyron_bridge.sh
```
Leave this terminal open. You should see `[ws] starting WebSocket server` and `[serial] connected`.

**3. Open and run the app from THIS folder**
```bash
open "/Users/pingashvohra/Desktop/untitled folder 2/Aeyron/ReactivChallengeKit/ReactivChallengeKit.xcodeproj"
```
In Xcode: choose your iPhone (or Simulator), then Run (⌘R). Open the AEYRON Health clip.

**4. Check**
- Bridge terminal: `[ws] client connected` when the clip opens.
- App: heart rate / breaths per min update from the bridge (or 0/0 if no ESP32 data yet).

Device on hotspot: default Mac IP is 172.20.10.14. Otherwise use `?bridge=YOUR_MAC_IP` in the clip URL.
