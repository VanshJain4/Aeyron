# AEYRON Bridge — Commands to Run

## 1. Keep the bridge running

**In Terminal (leave this window open):**

```bash
cd /Users/pingashvohra/Desktop/reactivapp-clipkit-lab
./run_aeyron_bridge.sh
```

- Plug in the ESP32 via USB first (close Arduino Serial Monitor if it’s open).
- You should see `[ws] starting WebSocket server on ws://0.0.0.0:8765` and then `[sensor]` lines. Leave this running while you use the app.

**If the ESP32 port is different (e.g. usbmodem1102):**

```bash
SERIAL_PORT=/dev/cu.usbmodem1102 ./run_aeyron_bridge.sh
```

---

## 2. Keep port 8765 open (macOS firewall)

If the iPhone still can’t connect (timeout), the Mac firewall may be blocking incoming connections.

**Option A — Allow Python (recommended)**  
1. **System Settings** → **Network** → **Firewall** (or **Security & Privacy** → **Firewall**).  
2. Click **Options**.  
3. Click **+** and add **Python** (or **Terminal** if you run the bridge from Terminal).  
4. Set it to **Allow incoming connections**.  
5. Click **OK**.

**Option B — Turn off firewall temporarily (for testing only)**  
- System Settings → Network → Firewall → turn **Off** while testing. Turn it back **On** when done.

**Check that the bridge is listening:**

```bash
lsof -i :8765
```

You should see `python3` listening on port 8765. If you see nothing, the bridge isn’t running or didn’t start correctly.

---

## 3. Confirm your Mac IP (for the app)

If you change networks, get the Mac’s WiFi IP:

```bash
ipconfig getifaddr en0
```

If the result is **not** `10.200.12.200`, update `kBridgeURL` in  
`ReactivChallengeKit/ReactivChallengeKit/SensorWebSocketClient.swift` to  
`ws://<YOUR_IP>:8765` and rebuild the app.
