"""
TalentLens — Stage 4: Re-rank.

Takes the Top-K shortlist from Stage 3 (semantic retrieval) and computes a composite
score from four signals, then buckets each candidate into a fit band. Runs only on
the shortlist, never the full resume pool.

composite_score = w1*semantic_similarity + w2*skill_overlap + w3*experience_fit + w4*education_fit
(weights in config.COMPOSITE_WEIGHTS, each component scaled 0-100)

Run: python3 stage4_rerank.py <job_id>
"""
import json
import logging
import re
import sys

from config import (
    LOG_DIR,
    COMPOSITE_WEIGHTS,
    BAND_THRESHOLDS,
    DEGREE_LEVELS,
    TOP_K_RETRIEVAL,
)
from db import get_connection
from stage3_embed_index import retrieve_for_job_id

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stage4.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("stage4")

STOPWORDS = {
    "the", "and", "for", "with", "using", "skills", "knowledge", "eg", "ability",
    "including", "such", "etc", "strong", "good", "basic", "understanding",
    "to", "of", "in", "on", "is", "are", "as", "or", "an", "at", "by",
    "best", "practices", "practice", "detail", "attention", "solving", "problem",
    "collaboration", "communication", "technical", "proficiency", "proficient",
    "e.g", "eg.", "ie", "i.e",
}
TOKEN_RE = re.compile(r"[a-z0-9\+\#\.]{2,}")
EXPERIENCE_RANGE_RE = re.compile(r"(\d+)\s*to\s*(\d+)\s*Years?", re.IGNORECASE)
EXPERIENCE_PLUS_RE = re.compile(r"(\d+)\s*\+\s*Years?", re.IGNORECASE)
EXPERIENCE_DASH_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*Years?", re.IGNORECASE)
EXPERIENCE_MIN_RE = re.compile(r"(?:minimum|min\.?|at least)\s*(\d+)\s*Years?", re.IGNORECASE)
EXPERIENCE_BARE_RE = re.compile(r"(\d+)\s*Years?", re.IGNORECASE)


def tokenize(text: str):
    if not text:
        return set()
    tokens = TOKEN_RE.findall(text.lower())
    cleaned = {t.strip(".") for t in tokens}
    return {t for t in cleaned if t not in STOPWORDS and len(t) > 1}


def compute_skill_overlap(candidate_raw_text: str, jd_skills_text: str):
    """
    JD 'skills' text is a run of skill phrases (not cleanly comma-separated), so we
    compare at the token level rather than trying to split it into discrete phrases.
    Matched against the candidate's *full resume text* rather than just Stage 1's
    extracted skills list — the extractor only captures an explicit "Skills" section,
    but a real requirement (e.g. "server maintenance") is often mentioned in the
    experience bullets instead, and a recruiter would credit that too.
    Returns (score_0_100, matched_tokens, missing_tokens).
    """
    jd_tokens = tokenize(jd_skills_text)
    candidate_tokens = tokenize(candidate_raw_text)

    if not jd_tokens:
        return 0.0, [], []

    matched = jd_tokens & candidate_tokens
    missing = jd_tokens - candidate_tokens
    score = 100.0 * len(matched) / len(jd_tokens)
    return score, sorted(matched), sorted(missing)


def parse_min_years_required(jd_experience_text: str):
    """Extract a minimum-years requirement from free-form text — handles the
    dataset's 'X to Y Years' form as well as user-typed forms like '5+ years',
    '3-5 years', 'minimum 4 years', or a bare '5 years'. Returns None if nothing
    parseable is found (caller treats that as an unknown requirement)."""
    text = jd_experience_text or ""
    for pattern in (EXPERIENCE_RANGE_RE, EXPERIENCE_DASH_RE, EXPERIENCE_MIN_RE, EXPERIENCE_PLUS_RE, EXPERIENCE_BARE_RE):
        m = pattern.search(text)
        if m:
            return int(m.group(1))
    return None


def compute_experience_fit(candidate_years, jd_experience_text: str):
    """100 if candidate meets/exceeds the required minimum, linear falloff below it."""
    min_years = parse_min_years_required(jd_experience_text)
    if min_years is None:
        return 50.0  # unknown/unparseable requirement — neutral rather than penalized
    if candidate_years is None:
        return 0.0
    if candidate_years >= min_years or min_years == 0:
        return 100.0
    return max(0.0, 100.0 * candidate_years / min_years)


def parse_required_degree_level(jd_qualification: str):
    """Search for any recognized degree keyword anywhere in free-form qualification
    text (e.g. 'Bachelor's degree in Computer Science preferred') rather than
    requiring an exact single-token match — needed for user-typed JD input, and
    still matches the dataset's exact-code form ('M.Tech') as a special case."""
    if not jd_qualification:
        return None
    text = jd_qualification.strip().lower()
    exact = DEGREE_LEVELS.get(text.replace(".", ""))
    if exact is not None:
        return exact
    best = None
    for keyword, level in DEGREE_LEVELS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text):
            best = level if best is None else max(best, level)
    return best


def compute_education_fit(candidate_education: list, jd_qualification: str):
    """100 if candidate's highest degree level >= required level, partial credit if
    one level below, 0 otherwise. Unrecognized degree strings score neutral (50)."""
    required_level = parse_required_degree_level(jd_qualification)
    if required_level is None:
        return 50.0

    candidate_levels = [
        DEGREE_LEVELS.get(deg.strip().lower().replace(".", "").rstrip("s"))
        for deg in candidate_education
    ]
    candidate_levels = [lvl for lvl in candidate_levels if lvl is not None]
    if not candidate_levels:
        return 0.0

    best = max(candidate_levels)
    if best >= required_level:
        return 100.0
    if best == required_level - 1:
        return 50.0
    return 0.0


def band_for_score(score: float):
    if score >= BAND_THRESHOLDS["Strong Fit"]:
        return "Strong Fit"
    if score >= BAND_THRESHOLDS["High Potential"]:
        return "High Potential"
    if score >= BAND_THRESHOLDS["Needs Review"]:
        return "Needs Review"
    return "Low Fit"


def rerank_shortlist(job_id: str, k: int = TOP_K_RETRIEVAL):
    jd_row, retrieval_results = retrieve_for_job_id(job_id, k=k)
    conn = get_connection()

    candidates = []
    for resume_id, semantic_sim in retrieval_results:
        r = conn.execute(
            "SELECT structured_json, integrity_status, raw_text FROM resumes WHERE resume_id = ?",
            (resume_id,),
        ).fetchone()
        structured = json.loads(r["structured_json"] or "{}")

        semantic_score = max(0.0, min(1.0, semantic_sim)) * 100
        skill_score, matched_skills, missing_skills = compute_skill_overlap(
            r["raw_text"], jd_row["skills"]
        )
        experience_score = compute_experience_fit(
            structured.get("years_experience"), jd_row["experience"]
        )
        education_score = compute_education_fit(
            structured.get("education", []), jd_row["qualifications"]
        )

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
                "education": structured.get("education"),
                "integrity_status": r["integrity_status"],
            }
        )

    conn.close()
    candidates.sort(key=lambda c: c["composite_score"], reverse=True)

    band_counts = {"Strong Fit": 0, "High Potential": 0, "Needs Review": 0, "Low Fit": 0}
    for c in candidates:
        band_counts[c["band"]] += 1

    log.info(f"Reranked {len(candidates)} candidates for JD {job_id} ({jd_row['job_title']}). "
              f"Band counts: {band_counts}")
    return jd_row, candidates, band_counts


if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not job_id:
        print("Usage: python3 stage4_rerank.py <job_id>")
        sys.exit(1)

    jd_row, candidates, band_counts = rerank_shortlist(job_id)
    print(f"\nJD: {jd_row['job_title']} ({job_id})")
    print(f"Band counts: {band_counts}\n")
    for c in candidates[:15]:
        print(
            f"  [{c['band']:14s}] {c['composite_score']:5.1f} | {c['resume_id']} | "
            f"{c['headline']} | integrity={c['integrity_status']}"
        )
