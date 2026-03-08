# Checking if heart and breathing are correct

**Source matters.** If using the **SDK (Swift app)**, compare dashboard heart/breathing to a second source (e.g. watch, oximeter). If using the **Python bridge**, treat values as estimates only; use the steps below to sanity-check, but expect larger errors.

The bridge uses **your real camera**: **face** ROI for heart rate (rPPG), **chest** ROI (below the face) for breathing. No fake numbers — when we don’t have a reading yet we show "—" (measuring).

---

## Heart rate

1. **Manual pulse**  
   Count beats at your wrist or neck for **15 seconds**, multiply by **4** → beats per minute. Compare to the number on the dashboard. Expect ±5–15 BPM difference (camera rPPG is less accurate than a chest strap or oximeter).

2. **Fitness watch / oximeter**  
   If you have one, wear it and compare its heart rate to the dashboard. Again, some difference is normal.

3. **Rest vs movement**  
   Sit still: HR should be lower and more stable. Move or stand: HR should go up. If the displayed value doesn’t change at all over 1–2 minutes, the signal may be weak (light, face position).

---

## Breathing rate

1. **Count breaths**  
   Count how many times you **breathe in** (or out) in **1 minute**. Normal at rest is about 12–20/min. Compare to “Breathing rate” on the dashboard.

2. **Slow vs fast**  
   Breathe slowly (e.g. 6–8/min) for 30 seconds, then normally. The displayed rate should shift down then back up (may lag by 20–30 seconds because we use a buffer of data).

---

## When it’s “wrong”

- **Lighting**: Dim or uneven light hurts both HR and breathing. Use good, even light on your face.
- **Motion**: Moving or talking a lot adds noise. Sit still and face the camera for best results.
- **First 20–30 seconds**: Numbers can be unstable until the buffer fills. Wait a bit before comparing.
- **No face detected**: The bridge falls back to the center of the frame. Position your face clearly in view.

If you have a reference (watch, oximeter, manual count), use the steps above to check; small errors are expected with camera-based vitals.
