"""
TalentLens — Stage 6: What-if simulator.

Every skill mentioned in a JD gets a Mandatory / Preferred / Not Required toggle.
Recomputing on a toggle change is a pure function over the already-scored shortlist —
no re-embedding, no re-call to any LLM — so it can run live as the user flips toggles.

  - Mandatory skills the candidate lacks: disqualified (or penalized — configurable
    via config.MANDATORY_SKILL_MISS_PENALTY)
  - Preferred skills: weight into the recomputed skill score, don't disqualify
  - Not Required skills: excluded from scoring entirely

Run: python3 stage6_whatif.py <job_id>   — demonstrates a toggle scenario on the CLI
"""
import re
import sys

from config import COMPOSITE_WEIGHTS, BAND_THRESHOLDS, MANDATORY_SKILL_MISS_PENALTY
from db import get_connection
from stage4_rerank import tokenize, band_for_score, rerank_shortlist

PHRASE_SPLIT_RE = re.compile(r"(?<=[a-z\)])\s+(?=[A-Z])")


def _split_top_level(text: str, delimiters: str = ",;\n"):
    """Split on delimiter characters, but never inside parentheses — real JD skills
    text routinely has commas inside a parenthetical like '(e.g., AWS, Azure)', and
    those must not be treated as phrase boundaries."""
    parts = []
    current = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch in delimiters and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def extract_jd_skill_phrases(jd_skills_text: str):
    """
    Two supported input shapes:
      1. Comma/semicolon/newline-separated (what a user naturally types or pastes,
         e.g. "Python, Django, Docker") — split directly on those delimiters
         (parenthetical commas like "(e.g., AWS, Azure)" are protected — see
         _split_top_level). This is the expected shape for real user-typed input
         (Change 1).
      2. The bundled sample dataset's run-on 'skills' column, which has no *top-level*
         commas (line breaks appear to have been stripped upstream), e.g. "System
         administration Server maintenance Active Directory ...". Falls back to a
         lowercase-to-uppercase transition heuristic as a proxy for the original
         phrase boundary. Known limitation: back-to-back capitalized words in one
         phrase (e.g. "Active Directory") split into two — acceptable for a v1
         toggle list, not a scoring bug (each half still matches candidate text
         correctly on its own).
    """
    if not jd_skills_text:
        return []
    text = jd_skills_text.strip()
    top_level_parts = _split_top_level(text)
    if len(top_level_parts) > 1:
        parts = top_level_parts
    else:
        parts = PHRASE_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def compute_phrase_match(phrase: str, candidate_tokens: set) -> bool:
    phrase_tokens = tokenize(phrase)
    if not phrase_tokens:
        return False
    overlap = phrase_tokens & candidate_tokens
    return len(overlap) / len(phrase_tokens) >= 0.5


def prepare_snapshot(job_id: str, k: int = None):
    """One-time setup per JD: fetch the shortlist, precompute each candidate's token
    set and JD skill phrases. Everything after this is a fast pure recompute."""
    jd_row, candidates, _band_counts = rerank_shortlist(job_id, k=k) if k else rerank_shortlist(job_id)
    jd_row_dict = jd_row if isinstance(jd_row, dict) else dict(jd_row)
    phrases = extract_jd_skill_phrases(jd_row_dict["skills"])

    conn = get_connection()
    snapshot = []
    for c in candidates:
        row = conn.execute("SELECT raw_text FROM resumes WHERE resume_id = ?", (c["resume_id"],)).fetchone()
        candidate_tokens = tokenize(row["raw_text"])
        snapshot.append({**c, "candidate_tokens": candidate_tokens})
    conn.close()

    default_toggles = {p: "Preferred" for p in phrases}
    return {
        "jd_row": jd_row_dict,
        "phrases": phrases,
        "candidates": snapshot,
        "toggles": default_toggles,
    }


def recompute(snapshot: dict, toggle_states: dict):
    """Pure function: given the prepared snapshot and a toggle state per phrase,
    recompute skill score / composite score / band / qualification for every
    candidate. No DB, no embeddings, no LLM calls."""
    mandatory = [p for p in snapshot["phrases"] if toggle_states.get(p) == "Mandatory"]
    preferred = [p for p in snapshot["phrases"] if toggle_states.get(p) == "Preferred"]
    scoring_phrases = mandatory + preferred

    results = []
    for c in snapshot["candidates"]:
        tokens = c["candidate_tokens"]

        missing_mandatory = [p for p in mandatory if not compute_phrase_match(p, tokens)]
        qualified = len(missing_mandatory) == 0

        if not qualified and MANDATORY_SKILL_MISS_PENALTY == "disqualify":
            new_skill_score = 0.0
        elif scoring_phrases:
            matched = [p for p in scoring_phrases if compute_phrase_match(p, tokens)]
            new_skill_score = 100.0 * len(matched) / len(scoring_phrases)
            if not qualified and isinstance(MANDATORY_SKILL_MISS_PENALTY, (int, float)):
                new_skill_score = max(0.0, new_skill_score + MANDATORY_SKILL_MISS_PENALTY)
        else:
            new_skill_score = 100.0  # nothing mandatory/preferred selected

        new_composite = (
            COMPOSITE_WEIGHTS["semantic_similarity"] * c["semantic_score"]
            + COMPOSITE_WEIGHTS["skill_overlap"] * new_skill_score
            + COMPOSITE_WEIGHTS["experience_fit"] * c["experience_score"]
            + COMPOSITE_WEIGHTS["education_fit"] * c["education_score"]
        )
        new_band = band_for_score(new_composite) if qualified else "Disqualified"

        results.append(
            {
                "resume_id": c["resume_id"],
                "headline": c["headline"],
                "original_composite_score": c["composite_score"],
                "new_composite_score": round(new_composite, 1),
                "original_band": c["band"],
                "new_band": new_band,
                "qualified": qualified,
                "missing_mandatory": missing_mandatory,
            }
        )

    results.sort(key=lambda r: r["new_composite_score"], reverse=True)
    qualified_count = sum(1 for r in results if r["qualified"])

    return results, {"total_candidates": len(results), "qualified_count": qualified_count}


if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not job_id:
        print("Usage: python3 stage6_whatif.py <job_id>")
        sys.exit(1)

    snapshot = prepare_snapshot(job_id)
    print(f"JD: {snapshot['jd_row']['job_title']} ({job_id})")
    print(f"Extracted {len(snapshot['phrases'])} skill phrases:")
    for p in snapshot["phrases"]:
        print(f"  - {p}")

    # demo scenario: make the first two phrases Mandatory, leave the rest Preferred
    toggles = dict(snapshot["toggles"])
    for p in snapshot["phrases"][:2]:
        toggles[p] = "Mandatory"

    print(f"\nScenario: '{snapshot['phrases'][0]}' and '{snapshot['phrases'][1]}' set to Mandatory\n")
    baseline_results, baseline_summary = recompute(snapshot, snapshot["toggles"])
    results, summary = recompute(snapshot, toggles)
    print(
        f"Qualified before (all Preferred): {baseline_summary['qualified_count']}/"
        f"{baseline_summary['total_candidates']} -> "
        f"after (2 set Mandatory): {summary['qualified_count']}/{summary['total_candidates']}\n"
    )
    for r in results[:15]:
        print(
            f"  [{r['new_band']:12s}] {r['new_composite_score']:5.1f} "
            f"(was {r['original_composite_score']:5.1f}) | {r['resume_id']} | {r['headline']}"
            + (f" | MISSING: {r['missing_mandatory']}" if r["missing_mandatory"] else "")
        )
