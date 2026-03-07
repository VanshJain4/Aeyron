"use client";

import React, { useRef, useState } from "react";

const TEAL = "#0D9488";

export default function LiveCameraView() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [error, setError] = useState(null);
  const [live, setLive] = useState(false);
  const [asking, setAsking] = useState(false);

  const startCamera = async () => {
    const video = videoRef.current;
    if (!video) return;
    setAsking(true);
    setError(null);
    try {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      streamRef.current = stream;
      video.srcObject = stream;
      setLive(true);
    } catch (e) {
      setError(e.message || "Camera access denied");
      setLive(false);
    } finally {
      setAsking(false);
    }
  };

  if (error && !live) {
    return (
      <div style={styles.wrap}>
        <div style={styles.placeholder}>Camera unavailable: {error}</div>
        <button type="button" onClick={startCamera} style={styles.button} disabled={asking}>
          {asking ? "Asking…" : "Try again"}
        </button>
      </div>
    );
  }

  return (
    <div style={styles.wrap}>
      {!live && (
        <button type="button" onClick={startCamera} style={styles.button} disabled={asking}>
          {asking ? "Allow camera when prompted…" : "Start camera"}
        </button>
      )}
      {live && <span style={styles.badge}>LIVE</span>}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{ ...styles.video, display: live ? "block" : "none" }}
      />
    </div>
  );
}

const styles = {
  wrap: {
    position: "relative",
    backgroundColor: "#0f172a",
    borderRadius: 6,
    overflow: "hidden",
    minHeight: 240,
  },
  video: {
    width: "100%",
    height: "auto",
    display: "block",
    verticalAlign: "top",
  },
  badge: {
    position: "absolute",
    top: 8,
    left: 8,
    background: "#ef4444",
    color: "#fff",
    fontSize: "0.7rem",
    fontWeight: 700,
    padding: "4px 8px",
    borderRadius: 4,
    letterSpacing: "0.05em",
  },
  placeholder: {
    color: "#94a3b8",
    fontSize: "0.875rem",
    padding: "2rem",
    textAlign: "center",
  },
  button: {
    display: "block",
    margin: "1rem auto",
    padding: "10px 20px",
    background: TEAL,
    color: "#fff",
    border: "none",
    borderRadius: 6,
    fontSize: "0.9rem",
    fontWeight: 600,
    cursor: "pointer",
  },
};
