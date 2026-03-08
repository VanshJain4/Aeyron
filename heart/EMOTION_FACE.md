# Emotional face structure and variance / std thresholds

This describes the **face/emotion** data we use for Sentinel, aligned with Presage SmartSpectra’s Face and MicroExpression output, and how **variance** and **standard deviation** thresholds are used.

---

## 1. Presage face structure (from API/SDK)

Presage **MetricsBuffer** and edge **Metrics** expose a **Face** object with:

| Field | Type | Meaning |
|--------|------|--------|
| **blinking** | DetectionStatus[] | Blink events (time, detected, stable) |
| **talking** | DetectionStatus[] | Speech detection (time, detected, stable) |
| **landmarks** | Landmarks[] | Face mesh points (time, value = Point2dFloat[], stable, reset) |
| **microExpression** | MicroExpression[] | Emotion per frame |

**MicroExpression** (emotion from the face):

| Field | Type | Meaning |
|--------|------|--------|
| **expression** | string | Label e.g. `neutral`, `calm`, `anxious`, `distressed` |
| **confidence** | float | 0–1 confidence in that expression |
| **stable** | bool | Whether the reading is stable |
| **time** / **timestamp** | float / int64 | When it was observed |

So the API gives **expression** (label) and **confidence** (number). We use the **confidence** stream to compute variance and standard deviation over a rolling window.

---

## 2. What we do in the backend

- **POST /vitals** can include an optional **face** object:
  - `expression` (string)
  - `confidence` (float 0–1)
  - `blinking` (bool)
  - `talking` (bool)

- We push each **confidence** value into a **rolling buffer** (last N samples, default N = 30).

- We compute on that buffer:
  - **Variance** (σ²) of confidence
  - **Standard deviation** (σ) of confidence

- **Thresholds** (tunable via env):
  - **EMOTION_VARIANCE_THRESHOLD** (default `0.04`): breach when variance ≥ this.
  - **EMOTION_STD_THRESHOLD** (default `0.20`): breach when std ≥ this.

- **GET /vitals** returns:
  - `face` (last expression, confidence, blinking, talking)
  - `face_emotion_variance`, `face_emotion_std`
  - `face_emotion_variance_threshold`, `face_emotion_std_threshold`
  - `face_emotion_variance_breach`, `face_emotion_std_breach` (booleans)

---

## 3. Why variance and standard deviation?

- **High variance** of emotion confidence → expression is **changing a lot** (e.g. agitation, instability).
- **High std** → similar interpretation; spread of confidence is large.

So we use **variance** and **std** as simple, numeric proxies for “how much the emotional face signal is fluctuating.” When they go above the chosen thresholds, we flag a **threshold breach** for the dashboard (e.g. “Face / emotion” section in VitalsPanel).

---

## 4. Where the API key is used

- **Real Presage SDK**: when you integrate the actual Presage SDK (C++, Swift, or Android), you pass **PRESAGE_API_KEY** (from the environment) into the SDK’s auth/config. The SDK then returns **Face** and **MicroExpression** in its metrics; your backend can map those to the same **face** payload and confidence stream above.

- **Demo**: **presage_simulator.py** does not call Presage; it only **simulates** vitals + breathing_rate + face (expression + confidence + blinking/talking) and POSTs to our backend. So the API key is not used in the simulator. Use the key only when initializing the real Presage SDK.

---

## 5. Tuning the thresholds

- Defaults: variance = `0.04`, std = `0.20`. These are starting values; tune per use case.
- Set in environment (e.g. in `.env` or Vultr):
  - `EMOTION_VARIANCE_THRESHOLD=0.04`
  - `EMOTION_STD_THRESHOLD=0.20`
  - `EMOTION_ROLLING_WINDOW=30` (number of samples in the buffer).

Increase thresholds to reduce sensitivity; decrease to flag smaller fluctuations.
