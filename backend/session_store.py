"""
TalentLens backend — session store.

Holds each screening's state in memory (parsed resumes, candidates, JD, progress)
keyed by a screening_id. This is the multi-session equivalent of the Streamlit
app's st.session_state — same "session-only, no persistent resume data" design,
just addressable over HTTP instead of a browser session cookie.

This module does NOT contain any scoring/matching/parsing logic — it only calls
the existing, unmodified core_pipeline.py functions and tracks progress.
"""
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import shutil

import core_pipeline as cp
from stage6_whatif import recompute as whatif_recompute

import history_db

SCREENINGS: dict = {}
_LOCK = threading.Lock()

PIPELINE_STEPS = [
    ("parsing", "Parsing resumes and extracting candidate information"),
    ("integrity", "Running integrity checks"),
    ("indexing", "Building candidate index"),
    ("matching", "Matching skills, evaluating experience, and calculating compatibility"),
    ("bias_audit", "Auditing for bias"),
    ("explaining", "Generating match explanations"),
    ("done", "Ranking complete"),
]


def create_screening(jd_dict: dict, data_mode: str) -> str:
    screening_id = str(uuid.uuid4())
    with _LOCK:
        SCREENINGS[screening_id] = {
            "id": screening_id,
            "status": "pending",
            "step": None,
            "progress": 0.0,
            "error": None,
            "jd_dict": jd_dict,
            "data_mode": data_mode,
            "records": None,
            "candidates": None,
            "band_counts": None,
            "bias_summary": None,
            "flagged_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session_dir": None,
        }
    return screening_id


def get_screening(screening_id: str) -> dict:
    with _LOCK:
        s = SCREENINGS.get(screening_id)
        return dict(s) if s else None


def _set_progress(screening_id, step, progress):
    with _LOCK:
        if screening_id in SCREENINGS:
            SCREENINGS[screening_id]["step"] = step
            SCREENINGS[screening_id]["progress"] = progress
            SCREENINGS[screening_id]["status"] = "running"


def run_pipeline_async(screening_id: str, uploaded_files, top_k: int):
    thread = threading.Thread(
        target=_run_pipeline, args=(screening_id, uploaded_files, top_k), daemon=True
    )
    thread.start()


def _run_pipeline(screening_id: str, uploaded_files, top_k: int):
    try:
        s = get_screening(screening_id)
        jd_dict = s["jd_dict"]

        session_dir = Path(tempfile.mkdtemp(prefix=f"talentlens_{screening_id}_"))
        with _LOCK:
            SCREENINGS[screening_id]["session_dir"] = str(session_dir)

        _set_progress(screening_id, "parsing", 0.05)

        def parse_cb(done, total, resume_id):
            _set_progress(screening_id, "parsing", 0.05 + 0.30 * done / max(total, 1))

        records = cp.parse_uploaded_resumes(uploaded_files, session_dir, progress_callback=parse_cb)

        _set_progress(screening_id, "integrity", 0.38)

        def integrity_cb(done, total, resume_id):
            _set_progress(screening_id, "integrity", 0.38 + 0.22 * done / max(total, 1))

        cp.run_integrity_checks(records, progress_callback=integrity_cb)

        _set_progress(screening_id, "indexing", 0.62)
        index, resume_ids = cp.build_session_index(records)

        _set_progress(screening_id, "matching", 0.72)
        jd_text = f"{jd_dict['job_title']}. {jd_dict['job_description']} Skills: {jd_dict['skills']}"
        retrieval_results = cp.retrieve_top_k_session(jd_text, index, resume_ids, k=top_k)
        candidates, band_counts = cp.score_candidates_session(jd_dict, records, retrieval_results)

        _set_progress(screening_id, "bias_audit", 0.85)
        _audit_results, bias_summary = cp.run_bias_audit_session(jd_dict, candidates, records)

        _set_progress(screening_id, "explaining", 0.94)
        candidates = cp.run_explanations_session(jd_dict["job_title"], candidates)

        flagged_statuses = {"WARNING", "POTENTIAL MANIPULATION"}
        flagged_count = sum(1 for c in candidates if (c.get("integrity_status") or "") in flagged_statuses)

        with _LOCK:
            SCREENINGS[screening_id].update(
                {
                    "status": "done",
                    "step": "done",
                    "progress": 1.0,
                    "records": records,
                    "candidates": candidates,
                    "band_counts": band_counts,
                    "bias_summary": bias_summary,
                    "flagged_count": flagged_count,
                }
            )

        # Persist only metadata (never resume content) for the Dashboard's history —
        # a deliberate addition beyond the original single-session app; see README.
        history_db.record_screening(
            screening_id=screening_id,
            job_title=jd_dict["job_title"],
            data_mode=s["data_mode"],
            n_candidates=len(candidates),
            n_shortlisted=len(candidates),
            n_strong=band_counts.get("Strong Fit", 0),
            n_flagged=flagged_count,
            created_at=SCREENINGS[screening_id]["created_at"],
        )

    except Exception as e:
        with _LOCK:
            if screening_id in SCREENINGS:
                SCREENINGS[screening_id]["status"] = "error"
                SCREENINGS[screening_id]["error"] = str(e)


def recompute_whatif(screening_id: str, toggles: dict):
    s = get_screening(screening_id)
    if not s or s["status"] != "done":
        return None, None
    snapshot = cp.build_whatif_snapshot_session(s["jd_dict"], s["candidates"], s["records"])
    results, summary = whatif_recompute(snapshot, toggles)
    return results, summary


def get_whatif_phrases(screening_id: str):
    s = get_screening(screening_id)
    if not s or s["status"] != "done":
        return []
    snapshot = cp.build_whatif_snapshot_session(s["jd_dict"], s["candidates"], s["records"])
    return snapshot["phrases"]


def cleanup_screening_files(screening_id: str):
    s = get_screening(screening_id)
    if s and s.get("session_dir"):
        shutil.rmtree(s["session_dir"], ignore_errors=True)
