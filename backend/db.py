"""
TalentLens — SQLite schema and connection helper.
"""
import sqlite3
import json
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS resumes (
    resume_id TEXT PRIMARY KEY,          -- file stem, e.g. "26480367"
    category TEXT,                       -- source folder, e.g. "INFORMATION-TECHNOLOGY"
    file_path TEXT,
    raw_text TEXT,
    extraction_method TEXT,              -- "fitz" or "pdfplumber"
    num_pages INTEGER,
    structured_json TEXT,                -- JSON: name, skills, years_experience, education, job_titles, certifications
    spans_json TEXT,                     -- JSON: list of {text, size, color, bbox, page} — used in Stage 2
    parse_status TEXT,                   -- "OK", "EMPTY", "ERROR"
    parse_error TEXT,
    integrity_status TEXT,               -- "CLEAR", "WARNING", "POTENTIAL MANIPULATION" (Stage 2)
    integrity_issues_json TEXT,          -- JSON list of {check, detail, page}
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_descriptions (
    job_id TEXT PRIMARY KEY,
    job_title TEXT,
    role TEXT,
    job_description TEXT,
    skills TEXT,
    experience TEXT,
    qualifications TEXT,
    responsibilities TEXT,
    location TEXT,
    country TEXT,
    company TEXT,
    raw_row_json TEXT,                   -- full original row, for anything not modeled above
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """Add columns introduced after the initial schema, for DBs created by an earlier version."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(resumes)")}
    if "integrity_status" not in existing_cols:
        conn.execute("ALTER TABLE resumes ADD COLUMN integrity_status TEXT")
    if "integrity_issues_json" not in existing_cols:
        conn.execute("ALTER TABLE resumes ADD COLUMN integrity_issues_json TEXT")


def upsert_resume(conn, record: dict):
    conn.execute(
        """
        INSERT INTO resumes (resume_id, category, file_path, raw_text, extraction_method,
                              num_pages, structured_json, spans_json, parse_status, parse_error)
        VALUES (:resume_id, :category, :file_path, :raw_text, :extraction_method,
                :num_pages, :structured_json, :spans_json, :parse_status, :parse_error)
        ON CONFLICT(resume_id) DO UPDATE SET
            category=excluded.category,
            file_path=excluded.file_path,
            raw_text=excluded.raw_text,
            extraction_method=excluded.extraction_method,
            num_pages=excluded.num_pages,
            structured_json=excluded.structured_json,
            spans_json=excluded.spans_json,
            parse_status=excluded.parse_status,
            parse_error=excluded.parse_error
        """,
        record,
    )


def update_resume_integrity(conn, resume_id: str, integrity_status: str, integrity_issues_json: str):
    conn.execute(
        "UPDATE resumes SET integrity_status = ?, integrity_issues_json = ? WHERE resume_id = ?",
        (integrity_status, integrity_issues_json, resume_id),
    )


def upsert_job_description(conn, record: dict):
    conn.execute(
        """
        INSERT INTO job_descriptions (job_id, job_title, role, job_description, skills,
                                       experience, qualifications, responsibilities,
                                       location, country, company, raw_row_json)
        VALUES (:job_id, :job_title, :role, :job_description, :skills,
                :experience, :qualifications, :responsibilities,
                :location, :country, :company, :raw_row_json)
        ON CONFLICT(job_id) DO UPDATE SET
            job_title=excluded.job_title,
            role=excluded.role,
            job_description=excluded.job_description,
            skills=excluded.skills,
            experience=excluded.experience,
            qualifications=excluded.qualifications,
            responsibilities=excluded.responsibilities,
            location=excluded.location,
            country=excluded.country,
            company=excluded.company,
            raw_row_json=excluded.raw_row_json
        """,
        record,
    )
