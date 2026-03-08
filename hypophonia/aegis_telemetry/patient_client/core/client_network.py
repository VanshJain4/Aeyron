"""
SQLite session logs (5 voice features). Phase 1: after 5 sessions POST /api/enroll.
Phase 2: POST /api/infer with today's vector, store anomaly_score.
"""
import sqlite3
from datetime import date
from pathlib import Path

import requests


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "session_logs.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SCHEMA_PATH.exists():
        schema = SCHEMA_PATH.read_text()
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(schema)
        conn.commit()
        return conn
    conn = sqlite3.connect(DB_PATH)
    return conn


def log_session(
    patient_id: str,
    rms_mean: float,
    pitch_std: float,
    jitter: float,
    shimmer: float,
    hnr: float,
    anomaly_score: float | None = None,
) -> int:
    """Insert one session row. Returns row id."""
    session_date = date.today().isoformat()
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO session_logs (patient_id, session_date, rms_mean, pitch_std, jitter, shimmer, hnr, anomaly_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (patient_id, session_date, rms_mean, pitch_std, jitter, shimmer, hnr, anomaly_score),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id or 0


def update_anomaly_score(row_id: int, anomaly_score: float) -> None:
    conn = _conn()
    conn.execute("UPDATE session_logs SET anomaly_score = ? WHERE id = ?", (anomaly_score, row_id))
    conn.commit()
    conn.close()


def session_count(patient_id: str) -> int:
    conn = _conn()
    cur = conn.execute(
        "SELECT COUNT(*) FROM session_logs WHERE patient_id = ?", (patient_id,)
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_baseline_vectors(patient_id: str) -> list[list[float]]:
    """First 5 sessions' feature vectors for enroll. Order: rms_mean, pitch_std, jitter, shimmer, hnr."""
    conn = _conn()
    cur = conn.execute(
        """SELECT rms_mean, pitch_std, jitter, shimmer, hnr FROM session_logs
           WHERE patient_id = ? ORDER BY id LIMIT 5""",
        (patient_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [list(r) for r in rows]


def get_latest_vector(patient_id: str) -> list[float] | None:
    """Latest session's 5 features (for infer after we just inserted)."""
    conn = _conn()
    cur = conn.execute(
        """SELECT rms_mean, pitch_std, jitter, shimmer, hnr FROM session_logs
           WHERE patient_id = ? ORDER BY id DESC LIMIT 1""",
        (patient_id,),
    )
    row = cur.fetchone()
    conn.close()
    return list(row) if row else None


def enroll(base_url: str, patient_id: str) -> dict:
    """POST /api/enroll with 5x5 baseline from DB (legacy)."""
    vectors = get_baseline_vectors(patient_id)
    if len(vectors) != 5:
        return {"error": f"Need 5 baseline sessions, have {len(vectors)}"}
    return enroll_baseline_vectors(base_url, patient_id, vectors)


def enroll_baseline_vectors(base_url: str, patient_id: str, vectors: list[list[float]]) -> dict:
    """POST /api/enroll with N x 5 feature vectors (e.g. from 3 min baseline audio)."""
    url = f"{base_url.rstrip('/')}/api/enroll"
    r = requests.post(
        url,
        json={"patient_id": patient_id, "baseline_data": vectors},
        timeout=60,
    )
    if not r.ok:
        msg = r.text
        try:
            msg = r.json().get("detail", msg)
        except Exception:
            pass
        r.raise_for_status()  # raises with context
    return r.json()


def get_profile(base_url: str, patient_id: str) -> dict:
    """GET /api/profile/{patient_id} — threshold, scaler min/max, baseline loss."""
    url = f"{base_url.rstrip('/')}/api/profile/{patient_id}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def infer(base_url: str, patient_id: str, current_data: list[float]) -> dict:
    """POST /api/infer. current_data: 5 floats."""
    url = f"{base_url.rstrip('/')}/api/infer"
    r = requests.post(
        url,
        json={"patient_id": patient_id, "current_data": current_data},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
