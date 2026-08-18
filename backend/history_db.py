"""
TalentLens backend — screening history (Dashboard support).

Stores ONLY aggregate metadata about past screenings — job title, counts, date,
data source. Never resume content, never candidate PII, never parsed text. This
is new infrastructure added to support the Dashboard's "Recent Screening
Sessions" list; it does not change how any screening is scored or matched.

Separate SQLite file from the demo-mode talentlens.db used by the original
Streamlit CLI tools — this one is backend-runtime-only.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "screening_history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS screenings (
    screening_id TEXT PRIMARY KEY,
    job_title TEXT,
    data_mode TEXT,
    n_candidates INTEGER,
    n_shortlisted INTEGER,
    n_strong INTEGER,
    n_flagged INTEGER,
    created_at TEXT,
    status TEXT DEFAULT 'completed'
);
"""


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def record_screening(screening_id, job_title, data_mode, n_candidates, n_shortlisted, n_strong, n_flagged, created_at):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT OR REPLACE INTO screenings
           (screening_id, job_title, data_mode, n_candidates, n_shortlisted, n_strong, n_flagged, created_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed')""",
        (screening_id, job_title, data_mode, n_candidates, n_shortlisted, n_strong, n_flagged, created_at),
    )
    conn.commit()
    conn.close()


def get_recent_screenings(limit: int = 10):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM screenings ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dashboard_summary():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT
             COALESCE(SUM(n_candidates), 0) AS total_screened,
             COALESCE(SUM(n_shortlisted), 0) AS total_shortlisted,
             COALESCE(SUM(n_strong), 0) AS total_strong,
             COALESCE(SUM(n_flagged), 0) AS total_flagged,
             COUNT(*) AS total_screenings
           FROM screenings"""
    ).fetchone()
    conn.close()
    return dict(row)
