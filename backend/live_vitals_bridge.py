"""
Live vitals from webcam: camera -> heart + breathing + optional emotions (FER).
POSTs to backend every 1–2 s. Run with API on localhost:8000.
Optional: pip install fer  for real emotion detection (angry, happy, sad, etc.).
"""
import argparse
import time
import sys

import cv2
import numpy as np
import httpx

# Optional: real emotion from face (angry, disgust, fear, happy, sad, surprise, neutral)
try:
    from fer import FER
    FER_AVAILABLE = True
except ImportError:
    FER_AVAILABLE = False

BASE_URL = "http://localhost:8000"
SAMPLE_RATE = 15.0  # Hz
BUFFER_SEC = 20.0
MIN_BPM, MAX_BPM = 48, 150
MIN_BR, MAX_BR = 6, 30   # breaths/min
ROI_SCALE = 0.4
SMOOTH_N = 7  # median of last N readings to reduce jumpiness and 48/6 lock
# Reject peak if it's at min/max boundary and not clearly dominant (avoids wrong 48 bpm / 6 br)
MIN_PEAK_RATIO = 1.5  # peak power must be this many times median in-band power
BOUNDARY_REJECT_HZ = 0.15  # treat as "boundary" if within this many Hz of min/max


def get_face_and_chest_roi(frame, face_cascade):
    """Returns (face_roi for heart, chest_roi for breathing). Chest is below face."""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
    if len(faces) > 0:
        x, y, fw, fh = faces[0]
        # Face ROI: forehead/cheek (for heart rPPG)
        fx1 = x + int(fw * 0.15)
        fy1 = y + int(fh * 0.1)
        fx2 = x + int(fw * 0.85)
        fy2 = y + int(fh * 0.6)
        face_roi = frame[fy1:fy2, fx1:fx2]
        # Chest ROI: directly below face (moves with breathing)
        cx1 = x
        cy1 = min(y + fh, h - 1)
        cy2 = min(y + fh + int(fh * 1.3), h)
        cx2 = x + fw
        if cy2 > cy1 and cx2 > cx1:
            chest_roi = frame[cy1:cy2, cx1:cx2]
        else:
            chest_roi = None
        return face_roi, chest_roi
    margin = int(min(w, h) * ROI_SCALE)
    cx, cy = w // 2, h // 2
    face_roi = frame[cy - margin:cy + margin, cx - margin:cx + margin]
    # No face so no reliable chest; use lower center as proxy
    cy1 = min(cy + margin, h - 20)
    cy2 = min(cy + margin + 80, h)
    chest_roi = frame[cy1:cy2, cx - margin:cx + margin] if cy2 > cy1 else None
    return face_roi, chest_roi


def extract_signal(roi):
    if roi is None or roi.size == 0:
        return None
    g = np.mean(roi[:, :, 1])
    b, r = np.mean(roi[:, :, 0]), np.mean(roi[:, :, 2])
    return 0.7 * g + 0.15 * (r + b)


def extract_chest_signal(chest_roi):
    """Chest ROI: mean intensity + vertical gradient (motion with breath)."""
    if chest_roi is None or chest_roi.size == 0:
        return None
    gray = cv2.cvtColor(chest_roi, cv2.COLOR_BGR2GRAY)
    mean_val = np.mean(gray)
    # Vertical gradient magnitude (expansion/contraction)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    motion = np.mean(np.abs(gy))
    return mean_val + 0.3 * motion


def compute_bpm(signal_buffer):
    if len(signal_buffer) < 50:
        return None
    arr = np.array(signal_buffer, dtype=float)
    arr = arr - np.mean(arr)
    n = len(arr)
    fft = np.fft.rfft(arr)
    freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    lo, hi = MIN_BPM / 60.0, MAX_BPM / 60.0
    mask = (freqs >= lo) & (freqs <= hi)
    if not np.any(mask):
        return None
    power = np.abs(fft) ** 2
    power[~mask] = 0
    idx = np.argmax(power)
    bpm = round(freqs[idx] * 60.0, 1)
    in_band = power[mask]
    median_p = np.median(in_band[in_band > 0]) if np.any(in_band > 0) else 0
    peak_p = power[idx]
    if median_p > 0 and peak_p < MIN_PEAK_RATIO * median_p:
        return None
    at_lo = freqs[idx] < lo + BOUNDARY_REJECT_HZ
    at_hi = freqs[idx] > hi - BOUNDARY_REJECT_HZ
    if (at_lo or at_hi) and median_p > 0 and peak_p < 2.0 * median_p:
        return None
    return bpm


def compute_breathing_rate(chest_signal_buffer):
    """Breathing from chest ROI signal (actual chest movement)."""
    if len(chest_signal_buffer) < 80:
        return None
    arr = np.array(chest_signal_buffer, dtype=float)
    arr = arr - np.mean(arr)
    n = len(arr)
    fft = np.fft.rfft(arr)
    freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    lo, hi = MIN_BR / 60.0, MAX_BR / 60.0
    mask = (freqs >= lo) & (freqs <= hi)
    if not np.any(mask):
        return None
    power = np.abs(fft) ** 2
    power[~mask] = 0
    idx = np.argmax(power)
    br = round(freqs[idx] * 60.0, 1)
    in_band = power[mask]
    median_p = np.median(in_band[in_band > 0]) if np.any(in_band > 0) else 0
    peak_p = power[idx]
    if median_p > 0 and peak_p < MIN_PEAK_RATIO * median_p:
        return None
    at_lo = freqs[idx] < lo + BOUNDARY_REJECT_HZ
    at_hi = freqs[idx] > hi - BOUNDARY_REJECT_HZ
    if (at_lo or at_hi) and median_p > 0 and peak_p < 2.0 * median_p:
        return None
    return br


def get_emotion_from_frame(frame, detector):
    """Return (expression, confidence) or (None, 0)."""
    if detector is None or frame is None:
        return None, 0.0
    try:
        # FER expects RGB; OpenCV is BGR
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        emotions = detector.detect_emotions(rgb)
        if not emotions:
            return "neutral", 0.0
        # First face: dict like {'angry': 0.1, 'disgust': 0, 'fear': 0.2, 'happy': 0.05, 'sad': 0.1, 'surprise': 0.02, 'neutral': 0.52}
        scores = emotions[0].get("emotions") or {}
        if not scores:
            return "neutral", 0.0
        expression = max(scores, key=scores.get)
        confidence = float(scores[expression])
        return expression, confidence
    except Exception:
        return "neutral", 0.0


def run_live_bridge(camera_id=0, interval_sec=2.0):
    def log(msg, err=False):
        (sys.stderr if err else sys.stdout).write(msg + "\n")
        (sys.stderr if err else sys.stdout).flush()

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        log("Bridge: Could not open camera. Close other apps using the camera.", err=True)
        sys.exit(1)
    log("Bridge: camera opened.")
    emotion_detector = None
    if FER_AVAILABLE:
        try:
            emotion_detector = FER()
            log("Bridge: FER loaded.")
        except Exception as e:
            log(f"Bridge: FER skipped ({e}).", err=True)
    else:
        log("Bridge: pip install fer for emotion detection (optional).")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    url = f"{BASE_URL}/vitals"
    buffer_len = int(BUFFER_SEC * SAMPLE_RATE)
    signal_buffer = []       # face ROI -> heart
    chest_buffer = []        # chest ROI -> breathing (your actual chest movement)
    bpm_history, br_history = [], []  # for median smoothing (avoids 48/6 lock)
    last_post = 0.0
    frame_interval = 1.0 / SAMPLE_RATE

    log("Bridge: heart (face) + breathing (chest). POST every " + str(interval_sec) + " s.")

    try:
        while True:
            t0 = time.perf_counter()
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            face_roi, chest_roi = get_face_and_chest_roi(frame, face_cascade)
            val = extract_signal(face_roi)
            if val is not None:
                signal_buffer.append(val)
                if len(signal_buffer) > buffer_len:
                    signal_buffer.pop(0)
            chest_val = extract_chest_signal(chest_roi)
            if chest_val is not None:
                chest_buffer.append(chest_val)
                if len(chest_buffer) > buffer_len:
                    chest_buffer.pop(0)
            raw_bpm = compute_bpm(signal_buffer) if len(signal_buffer) >= 50 else None
            raw_br = compute_breathing_rate(chest_buffer) if len(chest_buffer) >= 80 else None
            now = time.perf_counter()
            if now - last_post >= interval_sec:
                last_post = now
                if raw_bpm is not None:
                    bpm_history.append(raw_bpm)
                    if len(bpm_history) > SMOOTH_N:
                        bpm_history.pop(0)
                if raw_br is not None:
                    br_history.append(raw_br)
                    if len(br_history) > SMOOTH_N:
                        br_history.pop(0)
                bpm = round(float(np.median(bpm_history)), 1) if bpm_history else raw_bpm
                br = round(float(np.median(br_history)), 1) if br_history else raw_br
                expression, emotion_conf = get_emotion_from_frame(frame, emotion_detector)
                if expression is None:
                    expression, emotion_conf = "neutral", 0.0
                payload = {
                    "heart_rate": bpm,
                    "hrv": (35.0 if bpm is not None else None),
                    "stress_score": 0.25,
                    "patient": "live",
                    "breathing_rate": br,
                    "source": "bridge",
                    "face": {
                        "expression": expression,
                        "confidence": round(emotion_conf, 3),
                        "blinking": False,
                        "talking": False,
                    },
                }
                try:
                    r = httpx.post(url, json=payload, timeout=5.0)
                    r.raise_for_status()
                    hr_str = f"{bpm} bpm" if bpm is not None else "measuring..."
                    br_str = f"{br}/min" if br is not None else "measuring..."
                    log(f"Bridge: POST ok  heart={hr_str}  breathing={br_str}")
                except httpx.ConnectError:
                    log("Bridge: POST failed — is the API running on port 8000?", err=True)
                except httpx.HTTPError as e:
                    log("Bridge: POST failed: " + str(e), err=True)
            elapsed = time.perf_counter() - t0
            sleep = max(0, frame_interval - elapsed)
            time.sleep(sleep)
    except KeyboardInterrupt:
        log("Bridge: stopping.")
    finally:
        cap.release()


def main():
    ap = argparse.ArgumentParser(description="Live vitals from webcam -> backend")
    ap.add_argument("--camera", type=int, default=0, help="Camera device index")
    ap.add_argument("--interval", type=float, default=2.0, help="Seconds between POSTs")
    args = ap.parse_args()
    run_live_bridge(camera_id=args.camera, interval_sec=args.interval)


if __name__ == "__main__":
    main()
