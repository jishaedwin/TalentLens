"""
TalentLens — Stage 5a: Bias audit (deterministic, runs before any LLM call).

For each candidate in a JD's reranked shortlist:
  - build a PII-masked copy of their resume text (name/location/DOB-ish signals
    stripped from the header region — see config.PII_MASK_HEADER_LINES)
  - recompute the exact same Stage 3 (semantic) + Stage 4 (composite) scoring on
    the masked version
  - report score_with_identity vs score_without_identity, and whether rank changed

This never claims "the system is unbiased" — it reports the measured difference,
positive or negative, and leaves interpretation to the reader, per spec.

Run: python3 stage5_bias_audit.py <job_id>
"""
import json
import logging
import re
import sys

import spacy

from config import LOG_DIR, PII_MASK_HEADER_LINES, COMPOSITE_WEIGHTS
from db import get_connection
from stage3_embed_index import embed_texts, retrieve_for_job_id
from stage4_rerank import (
    compute_skill_overlap,
    compute_experience_fit,
    compute_education_fit,
    band_for_score,
    rerank_shortlist,
)

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stage5_bias.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("stage5_bias")

_nlp = None
MASK_LABELS = {"PERSON": "[NAME]", "GPE": "[LOCATION]", "LOC": "[LOCATION]",
               "NORP": "[GROUP]", "DATE": "[DATE]"}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\-\.\s\(\)]{7,}\d)")


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def mask_pii(raw_text: str, header_lines: int = PII_MASK_HEADER_LINES):
    """
    Mask likely identity signals in the header region only (see module docstring for
    why the whole document isn't run through generic NER). Returns (masked_text,
    list of {label, original} for what was masked).
    """
    lines = raw_text.splitlines()
    header = "\n".join(lines[:header_lines])
    body = "\n".join(lines[header_lines:])

    masked_items = []

    def _mask_regex(pattern, label, text):
        def repl(m):
            masked_items.append({"label": label, "original": m.group()})
            return f"[{label}]"
        return pattern.sub(repl, text)

    header = _mask_regex(EMAIL_RE, "EMAIL", header)
    header = _mask_regex(PHONE_RE, "PHONE", header)

    doc = get_nlp()(header)
    new_header_parts = []
    last_end = 0
    for ent in doc.ents:
        if ent.label_ in MASK_LABELS:
            new_header_parts.append(header[last_end:ent.start_char])
            placeholder = MASK_LABELS[ent.label_]
            new_header_parts.append(placeholder)
            masked_items.append({"label": ent.label_, "original": ent.text})
            last_end = ent.end_char
    new_header_parts.append(header[last_end:])
    masked_header = "".join(new_header_parts)

    masked_text = masked_header + ("\n" + body if body else "")
    return masked_text, masked_items


def score_candidate(resume_id: str, raw_text: str, structured: dict, jd_row: dict, jd_embedding):
    """Run the same Stage 3 (semantic) + Stage 4 (composite) scoring used in
    rerank_shortlist, but on arbitrary (possibly masked) text supplied directly
    instead of pulling from the FAISS index — needed since the masked version isn't
    in the index."""
    import numpy as np

    resume_embedding = embed_texts([raw_text])[0]
    semantic_sim = float(np.dot(resume_embedding, jd_embedding))
    semantic_score = max(0.0, min(1.0, semantic_sim)) * 100

    skill_score, matched, missing = compute_skill_overlap(raw_text, jd_row["skills"])
    experience_score = compute_experience_fit(structured.get("years_experience"), jd_row["experience"])
    education_score = compute_education_fit(structured.get("education"), jd_row["qualifications"])

    composite = (
        COMPOSITE_WEIGHTS["semantic_similarity"] * semantic_score
        + COMPOSITE_WEIGHTS["skill_overlap"] * skill_score
        + COMPOSITE_WEIGHTS["experience_fit"] * experience_score
        + COMPOSITE_WEIGHTS["education_fit"] * education_score
    )
    return round(composite, 1)


def run_bias_audit(job_id: str, k: int = None):
    jd_row, candidates, _band_counts = rerank_shortlist(job_id, k=k) if k else rerank_shortlist(job_id)
    jd_row_dict = jd_row if isinstance(jd_row, dict) else dict(jd_row)

    jd_text = f"{jd_row_dict['job_title']}. {jd_row_dict['job_description']} Skills: {jd_row_dict['skills']}"
    jd_embedding = embed_texts([jd_text])[0]

    conn = get_connection()

    # original ranks, by resume_id, from the identity-scored list (already sorted desc)
    original_rank = {c["resume_id"]: i for i, c in enumerate(candidates)}

    audit_results = []
    for c in candidates:
        row = conn.execute(
            "SELECT raw_text, structured_json FROM resumes WHERE resume_id = ?", (c["resume_id"],)
        ).fetchone()
        structured = json.loads(row["structured_json"] or "{}")
        masked_text, masked_items = mask_pii(row["raw_text"])

        masked_score = score_candidate(c["resume_id"], masked_text, structured, jd_row_dict, jd_embedding)
        score_delta = round(masked_score - c["composite_score"], 1)

        audit_results.append(
            {
                "resume_id": c["resume_id"],
                "score_with_identity": c["composite_score"],
                "score_without_identity": masked_score,
                "score_delta": score_delta,
                "masked_items": masked_items,
                "original_rank": original_rank[c["resume_id"]],
            }
        )

    # recompute ranks under the masked scores to check rank stability
    by_masked_score = sorted(audit_results, key=lambda a: a["score_without_identity"], reverse=True)
    masked_rank = {a["resume_id"]: i for i, a in enumerate(by_masked_score)}
    for a in audit_results:
        a["masked_rank"] = masked_rank[a["resume_id"]]
        a["rank_change"] = a["original_rank"] - a["masked_rank"]

    conn.close()

    deltas = [a["score_delta"] for a in audit_results]
    rank_changes = [a["rank_change"] for a in audit_results]
    summary = {
        "n_candidates": len(audit_results),
        "mean_score_delta": round(sum(deltas) / len(deltas), 2) if deltas else 0,
        "max_abs_score_delta": max((abs(d) for d in deltas), default=0),
        "n_rank_changed": sum(1 for r in rank_changes if r != 0),
        "max_abs_rank_change": max((abs(r) for r in rank_changes), default=0),
    }
    log.info(f"Bias audit for JD {job_id}: {summary}")
    return jd_row_dict, audit_results, summary


if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not job_id:
        print("Usage: python3 stage5_bias_audit.py <job_id>")
        sys.exit(1)

    jd_row, audit_results, summary = run_bias_audit(job_id)
    print(f"\nBias audit — JD: {jd_row['job_title']} ({job_id})")
    print(f"Summary: {summary}\n")
    for a in sorted(audit_results, key=lambda x: abs(x["score_delta"]), reverse=True)[:10]:
        print(
            f"  {a['resume_id']}: with_identity={a['score_with_identity']:.1f} "
            f"without_identity={a['score_without_identity']:.1f} "
            f"delta={a['score_delta']:+.1f} rank_change={a['rank_change']:+d} "
            f"masked={[m['label'] for m in a['masked_items']]}"
        )
