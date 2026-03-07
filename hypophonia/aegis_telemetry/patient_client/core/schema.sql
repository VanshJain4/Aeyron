-- Session logs: one row per recording session. Voice-only (hypophonia): 5 features.
CREATE TABLE IF NOT EXISTS session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    session_date TEXT NOT NULL,
    rms_mean REAL,
    pitch_std REAL,
    jitter REAL,
    shimmer REAL,
    hnr REAL,
    anomaly_score REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_session_logs_patient_date ON session_logs(patient_id, session_date);
