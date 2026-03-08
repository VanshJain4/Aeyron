# AEYRON Health Clip — Files Used (Clip → Device) for GitHub Submission

This list includes every file and artifact used in the pipeline: **ESP32 sensor → bridge → iOS app clip**.

---

## 1. iOS App / Clip (Swift)

All under `ReactivChallengeKit/ReactivChallengeKit/` unless noted.

| File | Purpose |
|------|--------|
| `Examples/ AeyronHealthClip.swift` | AEYRON clip, dashboard UI, VitalsEngine (camera/mic + sensor fusion) |
| `SensorWebSocketClient.swift` | WebSocket client; connects to bridge, pushes heart_rate/breath_rate into VitalsEngine |
| `Simulator/ClipRouter.swift` | Registers AeyronHealthClip; URL matching and sample URL for `aeyron.health/patient/:patientId` |
| `Protocol/ClipExperience.swift` | Clip protocol (urlPattern, clipName, body, etc.) |
| `Protocol/ClipContext.swift` | Invocation context (URL, pathParameters, queryParameters) |
| `ReactivChallengeKitApp.swift` | App entry; creates ClipRouter, hosts SimulatorShell |
| `Simulator/SimulatorShell.swift` | Root shell; shows LandingView or active clip |
| `Simulator/LandingView.swift` | Home screen; lists clips (including AEYRON), journey timeline |
| `Simulator/InvocationConsole.swift` | URL input for invoking clips |
| `Simulator/ConstraintBanner.swift` | App Clip–style top banner |
| `Simulator/MomentTimer.swift` | 30-second clip timer |

**Project / build:**

| File | Purpose |
|------|--------|
| `ReactivChallengeKit/ReactivChallengeKit.xcodeproj/` | Xcode project (builds the app) |
| `ReactivChallengeKit/ReactivChallengeKit/Assets.xcassets/` | App icons, accent color (used by app) |

---

## 2. Bridge (Python — laptop)

| File | Purpose |
|------|--------|
| `aeyron_bridge.py` | Reads ESP32 serial (MR60BHA2), parses heart_rate/breath_rate/distance/phases, broadcasts JSON over WebSocket (port 8765) |
| `run_aeyron_bridge.sh` | Optional: kills process on serial port, then runs `aeyron_bridge.py` |

**Dependencies:** `pyserial`, `websockets` (`pip install pyserial websockets`).

---

## 3. Hardware / firmware (outside this repo)

| Item | Purpose |
|------|--------|
| `mmwavebreath.ino` | Arduino sketch on ESP32; uses Seeed MR60BHA2 library, prints `heart_rate`, `breath_rate`, `distance`, phases over Serial @ 115200 |
| **Library** | Seeed_Arduino_mmWave (MR60BHA2) |
| **Board** | XIAO_ESP32C6 (or similar); USB port e.g. `/dev/cu.usbmodem1101` |

---

## 4. Config / docs (optional for submission)

| File | Purpose |
|------|--------|
| `ReactivChallengeKit/CONSTRAINTS.md` | App Clip constraints (ephemeral, ≤30s, etc.) |
| `ReactivChallengeKit/SUBMISSION.md` | Challenge submission instructions (if present) |
| `CLAUDE.md` | Project overview and architecture (reference) |
| `README.md` | Repo readme |

---

## 5. Minimal file list (copy-paste for submission)

Only the files that are **required** for the AEYRON clip → device flow:

```
ReactivChallengeKit/ReactivChallengeKit/Examples/ AeyronHealthClip.swift
ReactivChallengeKit/ReactivChallengeKit/SensorWebSocketClient.swift
ReactivChallengeKit/ReactivChallengeKit/Simulator/ClipRouter.swift
ReactivChallengeKit/ReactivChallengeKit/Protocol/ClipExperience.swift
ReactivChallengeKit/ReactivChallengeKit/Protocol/ClipContext.swift
ReactivChallengeKit/ReactivChallengeKit/ReactivChallengeKitApp.swift
ReactivChallengeKit/ReactivChallengeKit/Simulator/SimulatorShell.swift
ReactivChallengeKit/ReactivChallengeKit/Simulator/LandingView.swift
ReactivChallengeKit/ReactivChallengeKit/Simulator/InvocationConsole.swift
ReactivChallengeKit/ReactivChallengeKit/Simulator/ConstraintBanner.swift
ReactivChallengeKit/ReactivChallengeKit/Simulator/MomentTimer.swift
ReactivChallengeKit/ReactivChallengeKit.xcodeproj/
ReactivChallengeKit/ReactivChallengeKit/Assets.xcassets/
aeyron_bridge.py
run_aeyron_bridge.sh
```

**Note:** The project uses **PBXFileSystemSynchronizedRootGroup**, so the entire `ReactivChallengeKit/ReactivChallengeKit/` folder is part of the Xcode target. For a clean GitHub submission you typically push the **whole repo**; the list above is what is **used** for the AEYRON clip → device path specifically.
