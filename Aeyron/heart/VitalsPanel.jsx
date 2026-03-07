"use client";

import React, { useEffect, useState, useRef } from "react";

const TEAL = "#0D9488";
const POLL_MS = 2000;
const VITALS_URL = process.env.NEXT_PUBLIC_VITALS_API || "http://localhost:8000";

export default function VitalsPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const prevHrvRef = useRef(null);

  useEffect(() => {
    const fetchVitals = async () => {
      try {
        const res = await fetch(`${VITALS_URL}/vitals`);
        if (!res.ok) throw new Error(res.statusText);
        const json = await res.json();
        setData((prev) => {
          if (prev && json.hrv != null) prevHrvRef.current = prev.hrv;
          return json;
        });
        setError(null);
      } catch (e) {
        setError(e.message);
      }
    };

    fetchVitals();
    const id = setInterval(fetchVitals, POLL_MS);
    return () => clearInterval(id);
  }, []);

  if (error) {
    return (
      <div style={styles.panel}>
        <div style={styles.error}>Vitals unavailable: {error}</div>
      </div>
    );
  }

  if (!data || data.heart_rate == null) {
    return (
      <div style={styles.panel}>
        <div style={styles.placeholder}>Waiting for vitals…</div>
      </div>
    );
  }

  const hr = data.heart_rate;
  const hrv = data.hrv;
  const stressPct = data.stress_score != null ? Math.round(data.stress_score * 100) : 0;
  const risk = data.vitals_risk != null ? data.vitals_risk : 0;
  const hrOutOfRange = hr != null && (hr < 60 || hr > 100);
  const prevHrv = prevHrvRef.current;
  const hrvTrend =
    prevHrv != null && hrv != null
      ? hrv > prevHrv
        ? "up"
        : hrv < prevHrv
          ? "down"
          : "flat"
      : null;

  const stressColor = stressPct < 40 ? "#22c55e" : stressPct <= 70 ? "#eab308" : "#ef4444";

  return (
    <div style={styles.panel}>
      <div style={styles.section}>
        <span style={styles.label}>Heart rate</span>
        <span style={styles.value}>
          {hr != null ? Math.round(hr) : "—"}
          {hrOutOfRange && <span style={styles.flag} title="Outside 60–100 bpm"> ⚠</span>}
        </span>
        <span style={styles.unit}>bpm</span>
      </div>

      <div style={styles.section}>
        <span style={styles.label}>HRV</span>
        <span style={styles.value}>
          {hrv != null ? Math.round(hrv) : "—"}
          {hrvTrend === "up" && <span style={styles.trend}> ↑</span>}
          {hrvTrend === "down" && <span style={styles.trend}> ↓</span>}
        </span>
      </div>

      <div style={styles.section}>
        <span style={styles.label}>Stress</span>
        <div style={styles.barWrap}>
          <div
            style={{
              ...styles.barFill,
              width: `${stressPct}%`,
              backgroundColor: stressColor,
            }}
          />
        </div>
        <span style={styles.unit}>{stressPct}%</span>
      </div>

      <div style={styles.riskSection}>
        <span style={styles.riskLabel}>Vitals risk</span>
        <span style={styles.riskValue}>{risk.toFixed(2)}</span>
        <span style={styles.riskRange}>/ 1.0</span>
      </div>
    </div>
  );
}

const styles = {
  panel: {
    backgroundColor: "#0f172a",
    color: "#e2e8f0",
    padding: "1rem 1.25rem",
    borderRadius: 6,
    fontFamily: "system-ui, sans-serif",
    minWidth: 280,
  },
  label: {
    display: "block",
    fontSize: "0.75rem",
    color: "#94a3b8",
    marginBottom: 2,
  },
  value: {
    fontSize: "1.25rem",
    fontWeight: 600,
    color: "#f1f5f9",
  },
  unit: {
    fontSize: "0.75rem",
    color: "#94a3b8",
    marginLeft: 4,
  },
  section: {
    marginBottom: "1rem",
  },
  flag: {
    color: "#ef4444",
    marginLeft: 4,
  },
  trend: {
    color: TEAL,
    marginLeft: 2,
  },
  barWrap: {
    height: 8,
    backgroundColor: "#1e293b",
    borderRadius: 4,
    overflow: "hidden",
    marginTop: 4,
    marginBottom: 2,
  },
  barFill: {
    height: "100%",
    borderRadius: 4,
    transition: "width 0.3s ease",
  },
  riskSection: {
    marginTop: "1.25rem",
    paddingTop: "1rem",
    borderTop: `1px solid #334155`,
  },
  riskLabel: {
    display: "block",
    fontSize: "0.75rem",
    color: "#94a3b8",
    marginBottom: 4,
  },
  riskValue: {
    fontSize: "1.5rem",
    fontWeight: 700,
    color: TEAL,
  },
  riskRange: {
    fontSize: "0.875rem",
    color: "#64748b",
    marginLeft: 4,
  },
  placeholder: {
    color: "#64748b",
    fontSize: "0.875rem",
  },
  error: {
    color: "#f87171",
    fontSize: "0.875rem",
  },
};
