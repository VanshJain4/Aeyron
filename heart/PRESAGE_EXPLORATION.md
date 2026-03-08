# Presage SmartSpectra – Heart/Pulse Exploration

Exploration summary of the [SmartSpectra SDK](https://github.com/Presage-Security/SmartSpectra) for use in the **Aeyron heart** module. The repo is cloned **outside** `Aeyron/Aeyron` at:

**`/Users/pingashvohra/Aeyron/SmartSpectra`**

---

## 1. Heart-relevant features (from README)

- **Cardiac waveform**: Real-time pulse pleth waveform, pulse rate, and heart rate variability (HRV).
- **Pulse–respiration quotient**: Cardio-respiratory coupling (in `Pulse` protobuf).
- **Strict pulse**: High-precision pulse value (e.g. spot measurement).
- **Confidence**: Pulse rate comes with confidence; SDK has `is_pulse_high_confidence(snr)` in C++.

HRV is mentioned in docs/samples but noted as “when hrv is added to protobuf” / 60s SDK in comments—confirm current API if you need HRV.

---

## 2. Repo layout (relevant to heart)

| Path | Purpose |
|------|--------|
| `SmartSpectra/cpp/` | C++ SDK: containers, GUI, samples. **Core metrics** = `MetricsBuffer` (pulse, breathing, etc.) from Physiology REST API. |
| `SmartSpectra/swift/` | iOS SDK (Swift PM). Same metrics via `Presage_Physiology_Pulse`, `Presage_Physiology_MetricsBuffer`. |
| `SmartSpectra/android/` | Android SDK. `MetricsProto.Pulse`, same concepts. |
| `SmartSpectra/docs/` | High-level docs. **C++ metrics details**: `SmartSpectra/cpp/docs/metrics_usage.md`. |

---

## 3. Pulse data model (shared across C++ / Swift / Android)

From **Core metrics** (`MetricsBuffer`), the **Pulse** structure is:

- **`rate`**: `repeated MeasurementWithConfidence` — pulse rate (BPM) with `time`, `value`, `confidence`, `stable`.
- **`trace`**: `repeated Measurement` — pulse pleth waveform (`time`, `value`, `stable`).
- **`pulse_respiration_quotient`**: Cardio-respiratory coupling.
- **`strict`**: High-precision pulse value (e.g. for spot readings).

**C++**: `metrics.pulse().rate()`, `metrics.pulse().trace()`, etc.  
**Swift**: `metrics.pulse.rate`, `metrics.pulse.trace` (e.g. `metrics.pb.swift`).  
**Android**: `metrics.pulse` → `Pulse` with `rateList`, `traceList`, etc.

---

## 4. Where pulse is used in SmartSpectra

- **C++**
  - **README Hello Vitals**: `SetOnCoreMetricsOutput` → read `metrics.pulse().rate().rbegin()->value()` and `metrics.breathing().rate()`.
  - **`cpp/docs/metrics_usage.md`**: Full Core metrics access pattern and `Pulse` struct.
  - **`cpp/smartspectra/gui/opencv_hud.cpp`**: `UpdateWithNewMetrics()` → `new_metrics.pulse().rate()`, `new_metrics.pulse().trace()` for HUD.
  - **`cpp/samples/rest_continuous_example/main.cc`**: Core metrics callback; can log/save JSON (includes pulse).
  - **Confidence**: `cpp/smartspectra/gui/confidence_thresholding.hpp/.cpp` — `is_pulse_high_confidence(float snr)`.

- **Swift**
  - **`swift/sdk/.../ContinuousVitalsPlotView.swift`**: Live pulse trace and pulse rate from `sdk.metricsBuffer?.pulse` (trace + rate).
  - **`swift/samples/smartspectra-trials/ContentView.swift`**: Sections for “Pulse” (pleth, rates, confidence); HRV placeholder in comments.
  - **`swift/sdk/.../SmartSpectraSwiftSDK.docc/SmartSpectraSwiftSDK.md`**: Docs reference pulse rate and cardiac waveform.

- **Android**
  - **`android/sdk/.../screening_plot.xml`**: “Pulse Rate” label and pulse plot.
  - **`android/samples/.../MainActivity.kt`** (trials): Charts for pulse pleth, pulse rates, pulse rate confidence; HRV TODO in comments.
  - **`android/README.md`**: Describes `Pulse` (rate, trace, strict) and continuous mode with live pulse/breathing.

---

## 5. Integration options for Aeyron heart

- **C++ (Mac/Linux)**: Use SmartSpectra container + `SetOnCoreMetricsOutput`; consume `metrics.pulse()` (rate, trace, strict). See `cpp/README.md` and `cpp/docs/metrics_usage.md`. Prebuilt: Ubuntu 22.04/Mint 21; macOS from-source (see `docs/build_macos.md`).
- **iOS**: Add SmartSpectra Swift package; use `SmartSpectraSwiftSDK` and `metricsBuffer.pulse` (rate, trace). See `swift/README.md`.
- **Android**: Add SmartSpectra Android SDK; use `metrics.pulse` (rateList, traceList, etc.). See `android/README.md`.

Auth: API key (and OAuth on iOS/Android). Get key at https://physiology.presagetech.com.  
Docs: https://docs.physiology.presagetech.com/

---

## 6. Key files (quick reference)

| What | File |
|------|------|
| C++ metrics usage & Pulse struct | `SmartSpectra/cpp/docs/metrics_usage.md` |
| C++ quick start (pulse in callback) | `SmartSpectra/cpp/README.md` (Hello Vitals) |
| C++ HUD pulse update | `SmartSpectra/cpp/smartspectra/gui/opencv_hud.cpp` |
| Swift Pulse / MetricsBuffer types | `SmartSpectra/swift/sdk/.../metrics.pb.swift` |
| Swift live pulse UI | `SmartSpectra/swift/sdk/.../ContinuousVitalsPlotView.swift` |
| Android Pulse in Java | `SmartSpectra/android/sdk/.../proto/MetricsProto.java` (Pulse) |
| Confidence (C++) | `SmartSpectra/cpp/smartspectra/gui/confidence_thresholding.hpp` |

---

## 7. Suggested next steps for heart folder

1. **Choose platform**: C++ (desktop), Swift (iOS), or Android for the heart module.
2. **Dependency**: Link/import SmartSpectra from `../SmartSpectra` (or system-installed C++ package) and add auth (API key).
3. **Abstraction**: Implement a thin “heart service” or “vitals source” that:
   - Depends on SmartSpectra (or a small interface that can be implemented by SmartSpectra).
   - Exposes only what the heart module needs (e.g. latest pulse rate, optional trace, confidence).
   - Keeps UI, business logic, and data access separate per project rules.

This file is reference only; no SmartSpectra code is duplicated here.
