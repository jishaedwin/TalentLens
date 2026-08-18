"""
TalentLens — core session pipeline (Change 1: real user input only).

Runs Stages 1-6 entirely from what the user uploads in the *current session* — no
SQLite, no persistent FAISS index file, no fallback to the bundled sample dataset.
The standalone stageN_*.py scripts and talentlens.db are separate offline/demo-mode
tooling for local testing — this module and app.py never touch them.

Most of the actual scoring/audit/explanation logic already lived in pure functions
in stage4-6 (no DB dependency) — this module adds the missing session-scoped pieces:
uploaded-file parsing, an in-memory FAISS index, and thin wrappers that assemble
those pure functions into one session pipeline.
"""
import json
from pathlib import Path

import faiss

from config import COMPOSITE_WEIGHTS, DEMO_RESUME_DIR, DEMO_JOB
from stage1_resume_parser import parse_resume
from stage2_integrity_check import run_integrity_check
from stage3_embed_index import embed_texts
from stage4_rerank import (
    compute_skill_overlap,
    compute_experience_fit,
    compute_education_fit,
    band_for_score,
    tokenize,
)
from stage5_bias_audit import mask_pii, score_candidate
from stage5_explain import generate_explanation
from stage6_whatif import extract_jd_skill_phrases


def save_uploaded_pdf(uploaded_file, session_dir: Path) -> Path:
    """Write an in-memory uploaded file to a session-scoped persistent directory so
    the existing fitz/pdfplumber-based Stage 1/2 code (which takes a path and, for
    Stage 2's OCR check, re-opens the PDF) can read it for the life of the session."""
    dest = session_dir / uploaded_file.name
    with open(dest, "wb") as f:
        f.write(uploaded_file.getvalue())
    return dest


def parse_uploaded_resumes(uploaded_files, session_dir: Path, progress_callback=None):
    """Stage 1, session-scoped: parse every uploaded resume PDF, no DB write.
    Returns {resume_id: record_dict}."""
    records = {}
    for i, uf in enumerate(uploaded_files):
        path = save_uploaded_pdf(uf, session_dir)
        record = parse_resume(path, category="uploaded")
        records[record["resume_id"]] = record
        if progress_callback:
            progress_callback(i + 1, len(uploaded_files), record["resume_id"])
    return records


def run_integrity_checks(records: dict, progress_callback=None):
    """Stage 2, session-scoped. Mutates each record in place with integrity_status /
    integrity_issues — same checks as demo mode (validated against synthetic
    manipulated PDFs; see stage2_integrity_check.py)."""
    for i, (resume_id, record) in enumerate(records.items()):
        if record["parse_status"] != "OK":
            record["integrity_status"] = "UNKNOWN"
            record["integrity_issues"] = []
            continue
        spans = json.loads(record["spans_json"] or "[]")
        structured = json.loads(record["structured_json"] or "{}")
        status, issues = run_integrity_check(record, record["raw_text"], spans, structured)
        record["integrity_status"] = status
        record["integrity_issues"] = issues
        if progress_callback:
            progress_callback(i + 1, len(records), resume_id)
    return records


def build_session_index(records: dict):
    """Stage 3, session-scoped: embed only this session's uploaded (and OK-parsed)
    resumes, build a fresh in-memory FAISS index. No persistent index file — a new
    upload always gets a fresh index, never merges with a prior session's data."""
    ok_records = {rid: r for rid, r in records.items() if r["parse_status"] == "OK" and r["raw_text"]}
    resume_ids = list(ok_records.keys())
    texts = [ok_records[rid]["raw_text"] for rid in resume_ids]

    if not texts:
        return None, []

    embeddings = embed_texts(texts)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    return index, resume_ids


def retrieve_top_k_session(jd_text: str, index, resume_ids: list, k: int):
    """Stage 3 retrieval against the in-memory session index (not the persistent
    demo-mode index file)."""
    if index is None or not resume_ids:
        return []
    query_emb = embed_texts([jd_text])
    k = min(k, index.ntotal)
    scores, indices = index.search(query_emb, k)
    return [
        (resume_ids[idx], float(score))
        for idx, score in zip(indices[0], scores[0])
        if idx != -1
    ]


def score_candidates_session(jd_dict: dict, records: dict, retrieval_results: list):
    """Stage 4, session-scoped: same composite-scoring logic as demo-mode
    rerank_shortlist, but reading from the in-session records dict instead of SQLite."""
    candidates = []
    for resume_id, semantic_sim in retrieval_results:
        record = records[resume_id]
        structured = _structured(record)

        semantic_score = max(0.0, min(1.0, semantic_sim)) * 100
        skill_score, matched_skills, missing_skills = compute_skill_overlap(
            record["raw_text"], jd_dict.get("skills", "")
        )
        experience_score = compute_experience_fit(structured.get("years_experience"), jd_dict.get("experience", ""))
        education_score = compute_education_fit(structured.get("education", []), jd_dict.get("qualifications", ""))

        composite = (
            COMPOSITE_WEIGHTS["semantic_similarity"] * semantic_score
            + COMPOSITE_WEIGHTS["skill_overlap"] * skill_score
            + COMPOSITE_WEIGHTS["experience_fit"] * experience_score
            + COMPOSITE_WEIGHTS["education_fit"] * education_score
        )

        candidates.append(
            {
                "resume_id": resume_id,
                "composite_score": round(composite, 1),
                "band": band_for_score(composite),
                "semantic_score": round(semantic_score, 1),
                "skill_score": round(skill_score, 1),
                "experience_score": round(experience_score, 1),
                "education_score": round(education_score, 1),
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "headline": structured.get("headline"),
                "job_titles": structured.get("job_titles", []),
                "companies": structured.get("companies", []),
                "years_experience": structured.get("years_experience"),
                "education": structured.get("education", []),
                "integrity_status": record.get("integrity_status", "UNKNOWN"),
            }
        )

    candidates.sort(key=lambda c: c["composite_score"], reverse=True)
    band_counts = {"Strong Fit": 0, "High Potential": 0, "Needs Review": 0, "Low Fit": 0}
    for c in candidates:
        band_counts[c["band"]] += 1
    return candidates, band_counts


def run_bias_audit_session(jd_dict: dict, candidates: list, records: dict):
    """Stage 5a, session-scoped — reuses the same mask_pii/score_candidate pure
    functions as demo mode."""
    jd_text = f"{jd_dict.get('job_title', '')}. {jd_dict.get('job_description', '')} Skills: {jd_dict.get('skills', '')}"
    jd_embedding = embed_texts([jd_text])[0]

    original_rank = {c["resume_id"]: i for i, c in enumerate(candidates)}
    audit_results = []
    for c in candidates:
        record = records[c["resume_id"]]
        structured = _structured(record)
        masked_text, masked_items = mask_pii(record["raw_text"])
        masked_score = score_candidate(c["resume_id"], masked_text, structured, jd_dict, jd_embedding)
        audit_results.append(
            {
                "resume_id": c["resume_id"],
                "score_with_identity": c["composite_score"],
                "score_without_identity": masked_score,
                "score_delta": round(masked_score - c["composite_score"], 1),
                "masked_items": masked_items,
                "original_rank": original_rank[c["resume_id"]],
            }
        )

    by_masked = sorted(audit_results, key=lambda a: a["score_without_identity"], reverse=True)
    masked_rank = {a["resume_id"]: i for i, a in enumerate(by_masked)}
    for a in audit_results:
        a["masked_rank"] = masked_rank[a["resume_id"]]
        a["rank_change"] = a["original_rank"] - a["masked_rank"]

    deltas = [a["score_delta"] for a in audit_results]
    summary = {
        "n_candidates": len(audit_results),
        "mean_score_delta": round(sum(deltas) / len(deltas), 2) if deltas else 0,
        "max_abs_score_delta": max((abs(d) for d in deltas), default=0),
    }
    return audit_results, summary


def run_explanations_session(jd_title: str, candidates: list):
    """Stage 5b, session-scoped — attaches a chained-template evidence-grounded
    explanation paragraph (Change 2) to every candidate. Reuses the same
    generate_explanation()/validate_explanation() pipeline as demo mode."""
    for c in candidates:
        result = generate_explanation(c, jd_title)
        c["explanation"] = result["explanation"]
        c["explanation_source"] = result["source"]
    return candidates


def build_whatif_snapshot_session(jd_dict: dict, candidates: list, records: dict):
    """Stage 6, session-scoped snapshot prep — mirrors demo-mode prepare_snapshot()
    but reads from in-session records instead of SQLite."""
    phrases = extract_jd_skill_phrases(jd_dict.get("skills", ""))
    snapshot_candidates = []
    for c in candidates:
        record = records[c["resume_id"]]
        candidate_tokens = tokenize(record["raw_text"])
        snapshot_candidates.append({**c, "candidate_tokens": candidate_tokens})

    return {
        "jd_row": jd_dict,
        "phrases": phrases,
        "candidates": snapshot_candidates,
        "toggles": {p: "Preferred" for p in phrases},
    }


def _structured(record: dict):
    if isinstance(record.get("structured_json"), str):
        return json.loads(record["structured_json"] or "{}")
    return record.get("structured", {})


class LocalFileAsUpload:
    """Wraps a local file path in the same minimal interface Streamlit's
    UploadedFile exposes (.name, .getvalue()), so demo mode (Change 3) can feed
    the bundled sample PDFs through the exact same parse_uploaded_resumes() path
    real uploads use — no separate demo-specific parsing logic to maintain."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self.name = self._path.name

    def getvalue(self) -> bytes:
        return self._path.read_bytes()


def get_demo_uploaded_files():
    """The bundled demo resume set (Change 3) — same files every time, loaded
    through LocalFileAsUpload so they flow through the identical session
    pipeline real uploads do."""
    paths = sorted(DEMO_RESUME_DIR.glob("*.pdf"))
    return [LocalFileAsUpload(p) for p in paths]


def get_demo_jd():
    return dict(DEMO_JOB)
