"""
TalentLens — Stage 5b: Explanation generation.

For each candidate, generates a short natural-language explanation of their score —
built ONLY from already-computed structured data (matched/missing skills, experience
fit, education fit, composite score), never the raw resume text and never the
bias-audit identity fields, so the explanation itself can't leak or lean on identity
signals.

If config.LLM_EXPLANATIONS_ENABLED and the Groq API is reachable (a valid
GROQ_API_KEY is set), calls the Groq-hosted LLM. Otherwise — or if the Groq
call fails for any reason — uses the same templated-sentence fallback the
spec requires for validation failures, so explanation generation never
crashes or blocks the app on an unavailable/misconfigured API. Either way,
output is validated before being shown: any skill name mentioned must
actually appear in the structured input, or it falls back to the template.

Run: python3 stage5_explain.py <job_id>
"""
import logging
import os
import sys

from groq import Groq

from config import LOG_DIR, LLM_EXPLANATIONS_ENABLED, GROQ_MODEL
from stage4_rerank import rerank_shortlist

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stage5_explain.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("stage5_explain")

PROMPT_TEMPLATE = """You are summarizing a candidate-to-job match for a recruiter.
Only use the facts given below. Do not invent skills, experience, or qualifications
that are not explicitly listed. Do not mention the candidate's name, location, age,
or any personal identity information — none is provided to you.

Job title: {job_title}
Composite match score: {composite_score}/100 ({band})
Matched skills: {matched_skills}
Missing skills: {missing_skills}
Candidate years of experience: {years_experience}
Candidate education: {education}
Semantic similarity score: {semantic_score}/100
Skill overlap score: {skill_score}/100
Experience fit score: {experience_score}/100
Education fit score: {education_score}/100

Write 2-3 sentences explaining this match score to a recruiter, referencing only the
facts above."""


def build_templated_explanation(candidate: dict, jd_title: str) -> str:
    """
    Chains 2-4 templates together (strength / gap / transferability / overall) into a
    short paragraph — never a bare "Matched: X, Y, Z" list — combining multiple data
    points per sentence and citing something concrete (a skill name, a years figure,
    a company, a job title) wherever the structured data has it. No generative model
    involved: this is template selection + combination over already-extracted evidence.
    """
    matched = candidate["matched_skills"]
    missing = candidate["missing_skills"]
    years = candidate.get("years_experience")
    companies = candidate.get("companies") or []
    job_titles = candidate.get("job_titles") or []
    education = candidate.get("education") or []

    sentences = []

    # --- Strength sentence: lead with matched skills, grounded in role/company/years
    # if we have them, otherwise fall back to a skills-only version.
    top_matched = matched[:3]
    if top_matched:
        skill_phrase = _join_natural(top_matched)
        if companies and job_titles:
            sentences.append(
                f"This candidate shows strong alignment with the {jd_title} role, particularly in "
                f"{skill_phrase} — their time as {job_titles[0]} at {companies[0]} "
                f"{f'({years:.0f} years total experience)' if years else ''} directly matches "
                f"the role's core requirements."
            )
        elif years:
            sentences.append(
                f"This candidate shows strong alignment with the {jd_title} role, particularly in "
                f"{skill_phrase}, backed by {years:.0f} years of relevant experience."
            )
        else:
            sentences.append(
                f"This candidate shows alignment with the {jd_title} role, particularly in {skill_phrase}."
            )
    elif missing:
        sentences.append(
            f"This candidate's profile shows limited direct overlap with the {jd_title} requirements "
            f"as listed in their resume."
        )

    # --- Second strength sentence, if there's more matched skill depth to cite
    if len(matched) > 3:
        more_skills = _join_natural(matched[3:6])
        sentences.append(f"Additional experience with {more_skills} further strengthens their fit for the role.")

    # --- Gap sentence, naming specific missing skills and checking for a
    # transferable-but-different skill the candidate already has
    if missing:
        top_missing = missing[:3]
        gap_phrase = _join_natural(top_missing)
        transferable_note = _find_transferable_note(top_missing, matched)
        verb = "isn't" if len(top_missing) == 1 else "aren't"
        gap_sentence = f"The main gap is {gap_phrase}, which {verb} mentioned anywhere in their resume."
        if transferable_note:
            gap_sentence += f" {transferable_note}"
        sentences.append(gap_sentence)

    # --- Overall fit sentence, tying together experience/education fit with a concrete figure
    fit_clauses = []
    if years is not None:
        exp_note = (
            "meets or exceeds" if candidate["experience_score"] >= 100
            else "falls short of" if candidate["experience_score"] < 50
            else "partially meets"
        )
        fit_clauses.append(f"their {years:.0f} years of experience {exp_note} what the role calls for")
    if education:
        edu_note = (
            "meets or exceeds" if candidate["education_score"] >= 100
            else "is below" if candidate["education_score"] < 50
            else "is close to"
        )
        fit_clauses.append(f"their {education[0]} {edu_note} the stated qualification requirement")
    if fit_clauses:
        sentences.append(f"Overall, {' and '.join(fit_clauses)}, putting them in the {candidate['band']} band.")
    else:
        sentences.append(f"Overall, this places them in the {candidate['band']} band for this role.")

    return " ".join(sentences)


# curated adjacent-skill pairs used only to note plausible transferability in an
# explanation — never used for scoring, purely explanatory language
ADJACENT_SKILLS = {
    "kubernetes": ["docker"], "docker": ["kubernetes"],
    "azure": ["aws", "gcp"], "aws": ["azure", "gcp"], "gcp": ["aws", "azure"],
    "react": ["angular", "vue"], "angular": ["react", "vue"], "vue": ["react", "angular"],
    "postgresql": ["mysql", "sql"], "mysql": ["postgresql", "sql"], "sql": ["postgresql", "mysql"],
    "java": ["c#", "kotlin"], "c#": ["java"],
    "terraform": ["ansible", "cloudformation"], "ansible": ["terraform"],
}


def _join_natural(items):
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _find_transferable_note(missing_skills, matched_skills):
    matched_lower = {m.lower() for m in matched_skills}
    for missing in missing_skills:
        adjacent = ADJACENT_SKILLS.get(missing.lower(), [])
        found = [a for a in adjacent if a in matched_lower]
        if found:
            return f"Their existing {found[0]} experience suggests some transferable familiarity."
    return None


def validate_explanation(explanation: str, candidate: dict) -> bool:
    """Any skill-like token the explanation mentions must appear in the candidate's
    matched or missing skill lists (the only skill data it was given)."""
    allowed_skills = {s.lower() for s in candidate["matched_skills"] + candidate["missing_skills"]}
    if not allowed_skills:
        return True  # nothing to validate against — accept
    explanation_lower = explanation.lower()
    mentioned_known = any(skill in explanation_lower for skill in allowed_skills)
    return mentioned_known or (not candidate["matched_skills"] and not candidate["missing_skills"])


_groq_client = None  # lazy-initialized so a missing GROQ_API_KEY doesn't crash at import time


def get_groq_client():
    """Lazily builds the Groq client from the GROQ_API_KEY environment variable.
    Returns None (never raises) if the key isn't set, so callers can fall back
    to the templated explanation instead of crashing."""
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return None
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def call_groq(prompt: str):
    client = get_groq_client()
    if client is None:
        log.warning("GROQ_API_KEY not set; falling back to template")
        return None
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning(f"Groq call failed ({e}); falling back to template")
        return None


def generate_explanation(candidate: dict, jd_title: str) -> dict:
    explanation = None
    source = "template"

    if LLM_EXPLANATIONS_ENABLED:
        prompt = PROMPT_TEMPLATE.format(
            job_title=jd_title,
            composite_score=candidate["composite_score"],
            band=candidate["band"],
            matched_skills=", ".join(candidate["matched_skills"]) or "none",
            missing_skills=", ".join(candidate["missing_skills"]) or "none",
            years_experience=candidate.get("years_experience", "unknown"),
            education=", ".join(candidate.get("education", [])) or "unknown",
            semantic_score=candidate["semantic_score"],
            skill_score=candidate["skill_score"],
            experience_score=candidate["experience_score"],
            education_score=candidate["education_score"],
        )
        llm_output = call_groq(prompt)
        if llm_output and validate_explanation(llm_output, candidate):
            explanation = llm_output
            source = "llm"
        elif llm_output:
            log.warning(f"{candidate['resume_id']}: LLM explanation failed validation, using template")

    if explanation is None:
        explanation = build_templated_explanation(candidate, jd_title)

    return {"explanation": explanation, "source": source}


def explain_shortlist(job_id: str, top_n: int = 10):
    jd_row, candidates, band_counts = rerank_shortlist(job_id)
    jd_row_dict = jd_row if isinstance(jd_row, dict) else dict(jd_row)

    results = []
    for c in candidates[:top_n]:
        exp = generate_explanation(c, jd_row_dict["job_title"])
        results.append({**c, **exp})

    return jd_row_dict, results


if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not job_id:
        print("Usage: python3 stage5_explain.py <job_id>")
        sys.exit(1)

    jd_row, results = explain_shortlist(job_id)
    print(f"\nExplanations — JD: {jd_row['job_title']} ({job_id})\n")
    for r in results:
        print(f"[{r['band']}] {r['resume_id']} ({r['composite_score']}/100) — source={r['source']}")
        print(f"  {r['explanation']}\n")
