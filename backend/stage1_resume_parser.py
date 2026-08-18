"""
TalentLens — Stage 1: Resume intake & parsing.

For every resume PDF:
  - extract raw text (fitz primary, pdfplumber fallback on poor extraction)
  - extract per-span formatting metadata (font size, color, bbox, page) — needed by Stage 2
  - extract structured fields (name, skills, years_experience, education, job_titles, certifications)
  - store everything in SQLite

Run: python3 stage1_resume_parser.py
"""
import json
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber
import spacy

from config import RESUME_DIR, MIN_CHARS_FOR_GOOD_EXTRACTION, LOG_DIR
from db import init_db, get_connection, upsert_resume

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stage1.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("stage1")

nlp = spacy.load("en_core_web_sm")

SECTION_HEADERS = {
    "summary": {"professional summary", "summary", "profile", "objective"},
    "skills": {"skills", "core qualifications", "highlights", "technical skills", "areas of expertise"},
    "experience": {"experience", "work history", "professional experience", "employment history"},
    "education": {"education", "education and training", "academic background"},
    "certifications": {"certifications", "licenses", "licenses & certifications"},
}
ALL_HEADER_STRINGS = {h for group in SECTION_HEADERS.values() for h in group}

DEGREE_PATTERN = re.compile(
    r"\b(Ph\.?D\.?|Doctorate|Master(?:'?s)?(?: of [A-Za-z]+)?|M\.?S\.?|M\.?A\.?|M\.?B\.?A\.?|"
    r"Bachelor(?:'?s)?(?: of [A-Za-z]+)?|B\.?S\.?|B\.?A\.?|B\.?C\.?A\.?|Associate(?:'?s)?(?: Degree)?)\b",
    re.IGNORECASE,
)

DATE_RANGE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2}/\d{4}|\d{4})(?!\d)\s*(?:to|-|–)\s*(?<!\d)(\d{1,2}/\d{4}|\d{4}|Current|Present)(?!\d)",
    re.IGNORECASE,
)

CERT_KEYWORD_PATTERN = re.compile(r"\bcertifi\w*\b", re.IGNORECASE)


def extract_with_fitz(pdf_path: Path):
    """Return (full_text, spans, num_pages) using PyMuPDF."""
    doc = fitz.open(pdf_path)
    full_text_parts = []
    spans = []
    for page_num, page in enumerate(doc):
        page_dict = page.get_text("dict")
        page_rect = page.rect
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    color_int = span.get("color", 0)
                    r = (color_int >> 16) & 255
                    g = (color_int >> 8) & 255
                    b = color_int & 255
                    spans.append(
                        {
                            "text": text,
                            "size": round(span.get("size", 0), 2),
                            "color_rgb": [r, g, b],
                            "bbox": [round(v, 1) for v in span.get("bbox", [0, 0, 0, 0])],
                            "page": page_num,
                            "page_width": round(page_rect.width, 1),
                            "page_height": round(page_rect.height, 1),
                        }
                    )
        full_text_parts.append(page.get_text())
    full_text = "\n".join(full_text_parts)
    num_pages = len(doc)
    doc.close()
    return full_text, spans, num_pages


def extract_with_pdfplumber(pdf_path: Path):
    """Fallback extractor — text only, no span metadata (pdfplumber's span model differs)."""
    full_text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
        for page in pdf.pages:
            full_text_parts.append(page.extract_text() or "")
    return "\n".join(full_text_parts), num_pages


def clean_text(text: str) -> str:
    # normalize non-breaking spaces and other common PDF extraction artifacts
    text = text.replace("\xa0", " ").replace("Â", " ").replace("â€“", "-").replace("ï¼​", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def split_into_sections(text: str):
    """
    Walk the text line by line; whenever a line matches a known section header,
    start a new section. Returns dict: section_name -> list of lines.
    """
    sections = {"unlabeled": []}
    current = "unlabeled"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower().strip(":")
        matched_section = None
        for section_name, headers in SECTION_HEADERS.items():
            if lowered in headers:
                matched_section = section_name
                break
        if matched_section:
            current = matched_section
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


STOP_FRAGMENTS = {
    "and", "or", "the", "with", "for", "written", "oral", "office", "closing",
    "scheduling", "research", "integrity", "safety", "materials", "personnel",
    "direction", "inventory", "processes", "progress", "quality", "systems",
    "hardware", "automation", "mechanical", "coaching",
}


def extract_skills(sections: dict):
    skills = set()
    for key in ("skills",):
        for line in sections.get(key, []):
            # lines are often comma or colon separated lists; drop lines that read as
            # full prose sentences (end in a period, or start lowercase mid-thought)
            if line.endswith("."):
                continue
            parts = re.split(r"[,;]|\s{2,}", line)
            for p in parts:
                p = p.strip(" .\u2022-·").strip()
                if not p:
                    continue
                if not (1 < len(p) <= 40):
                    continue
                if p.lower() in STOP_FRAGMENTS:
                    continue
                # drop fragments that are clearly mid-sentence continuations (lowercase
                # start, more than 4 words, no real skill-like token)
                if p[:1].islower() and p.count(" ") > 3:
                    continue
                skills.add(p)
    return sorted(skills)


def extract_years_experience(full_text: str):
    """Sum up date-range durations found anywhere in the text (heuristic, not overlap-aware)."""
    total_months = 0
    matches = DATE_RANGE_PATTERN.findall(full_text)
    for start, end in matches:
        start_year = _year_of(start)
        end_year = 2026 if end.lower() in ("current", "present") else _year_of(end)
        # sanity bounds: reject implausible years (OCR/typo artifacts like "20004") and
        # any single stretch over 50 years, which can only be a mis-parsed range
        if not start_year or not (1960 <= start_year <= 2026):
            continue
        if not end_year or not (1960 <= end_year <= 2026):
            continue
        if end_year < start_year or (end_year - start_year) > 50:
            continue
        total_months += (end_year - start_year) * 12
    years = round(total_months / 12, 1)
    return years if years > 0 else None


def _year_of(token: str):
    m = re.search(r"\d{4}", token)
    return int(m.group()) if m else None


def extract_education(sections: dict, full_text: str):
    degrees = set()
    search_text = "\n".join(sections.get("education", [])) or full_text
    for m in DEGREE_PATTERN.finditer(search_text):
        degrees.add(m.group().strip())
    return sorted(degrees)


def extract_certifications(sections: dict, full_text: str):
    certs = set()
    for line in sections.get("certifications", []):
        certs.add(line.strip())
    for line in full_text.splitlines():
        if CERT_KEYWORD_PATTERN.search(line):
            certs.add(line.strip())
    return sorted(certs)


# bullet lines describing duties almost always start with an action verb in this dataset;
# real title lines are noun phrases, so excluding these cuts most false positives
BULLET_VERB_STARTS = {
    "ensure", "ensures", "manage", "manages", "managed", "interface", "interfaces",
    "perform", "performs", "performed", "coordinate", "coordinates", "develop",
    "develops", "developed", "maintain", "maintains", "maintained", "monitor",
    "monitors", "monitored", "identify", "identifies", "provide", "provides",
    "assist", "assists", "support", "supports", "supervise", "supervises",
    "responsible", "assemble", "assembled", "duties",
}


def extract_job_titles(sections: dict):
    titles = []
    for line in sections.get("experience", []):
        # a title line: short, no digits, no sentence-ending punctuation, no lowercase-only
        # start (which usually signals a wrapped sentence continuation)
        first_word = line.split(" ", 1)[0].strip(".,").lower()
        if (
            len(line) <= 60
            and not re.search(r"\d", line)
            and not line.endswith((".", ",", ";"))
            and "company name" not in line.lower()
            and line[:1].isupper()
            and line.count(" ") <= 6
            and first_word not in BULLET_VERB_STARTS
        ):
            titles.append(line.strip())
    # de-dup while preserving order
    seen = set()
    deduped = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped[:10]


NON_COMPANY_WORDS = {"and", "management", "engineering", "development", "assurance", "analysis",
                      "award", "awarded", "test", "equipment", "group", "department", "departments"}


def extract_companies(sections: dict):
    """Best-effort employer extraction — spaCy ORG entities, restricted to the
    experience section only (same false-positive-avoidance reasoning as elsewhere in
    this file: running generic NER over the whole resume mislabels tech jargon).
    Used for richer, evidence-citing explanations (Change 2) — not scored on, so a
    missed or extra company doesn't affect any score, only explanation wording.
    Noisier on this pre-redacted/anonymized sample dataset than it will be on real
    user-uploaded resumes with actual (non-placeholder) employer names."""
    experience_text = "\n".join(sections.get("experience", []))
    if not experience_text.strip():
        return []
    doc = nlp(experience_text[:3000])  # cap for speed on long experience sections
    companies = []
    seen = set()
    for ent in doc.ents:
        if ent.label_ != "ORG":
            continue
        name = ent.text.strip()
        if "\n" in name or "company name" in name.lower() or name.lower() == "current":
            continue
        words = set(name.lower().split())
        if words & NON_COMPANY_WORDS:
            continue
        if name.lower() not in seen and 2 < len(name) <= 50:
            seen.add(name.lower())
            companies.append(name)
    return companies[:10]


def extract_name(full_text: str, first_line: str):
    """Best-effort — this dataset is anonymized (redacted to 'Company Name' etc.), so a
    resume very often has no real person name in it at all. Try spaCy PERSON on the
    first two lines only, to avoid false positives from body text."""
    doc = nlp(first_line)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text
    return None


def parse_resume(pdf_path: Path, category: str):
    resume_id = pdf_path.stem
    try:
        raw_text, spans, num_pages = extract_with_fitz(pdf_path)
        extraction_method = "fitz"
        if len(raw_text.strip()) < MIN_CHARS_FOR_GOOD_EXTRACTION:
            log.warning(f"{resume_id}: fitz extraction too short ({len(raw_text.strip())} chars), trying pdfplumber")
            raw_text, num_pages = extract_with_pdfplumber(pdf_path)
            extraction_method = "pdfplumber"
            spans = []

        raw_text = clean_text(raw_text)

        if not raw_text.strip():
            return {
                "resume_id": resume_id,
                "category": category,
                "file_path": str(pdf_path),
                "raw_text": "",
                "extraction_method": extraction_method,
                "num_pages": num_pages,
                "structured_json": json.dumps({}),
                "spans_json": json.dumps(spans),
                "parse_status": "EMPTY",
                "parse_error": None,
            }

        sections = split_into_sections(raw_text)
        first_line = raw_text.strip().splitlines()[0] if raw_text.strip() else ""

        structured = {
            "name": extract_name(raw_text, first_line),
            "headline": first_line,
            "skills": extract_skills(sections),
            "years_experience": extract_years_experience(raw_text),
            "education": extract_education(sections, raw_text),
            "job_titles": extract_job_titles(sections),
            "companies": extract_companies(sections),
            "certifications": extract_certifications(sections, raw_text),
        }

        return {
            "resume_id": resume_id,
            "category": category,
            "file_path": str(pdf_path),
            "raw_text": raw_text,
            "extraction_method": extraction_method,
            "num_pages": num_pages,
            "structured_json": json.dumps(structured),
            "spans_json": json.dumps(spans),
            "parse_status": "OK",
            "parse_error": None,
        }

    except Exception as e:
        log.error(f"{resume_id}: parse error: {e}")
        return {
            "resume_id": resume_id,
            "category": category,
            "file_path": str(pdf_path),
            "raw_text": None,
            "extraction_method": None,
            "num_pages": None,
            "structured_json": json.dumps({}),
            "spans_json": json.dumps([]),
            "parse_status": "ERROR",
            "parse_error": str(e),
        }


def run():
    init_db()
    conn = get_connection()

    pdf_paths = sorted(RESUME_DIR.glob("*/*.pdf"))
    log.info(f"Found {len(pdf_paths)} resume PDFs under {RESUME_DIR}")

    status_counts = {"OK": 0, "EMPTY": 0, "ERROR": 0}
    for pdf_path in pdf_paths:
        category = pdf_path.parent.name
        record = parse_resume(pdf_path, category)
        upsert_resume(conn, record)
        status_counts[record["parse_status"]] += 1

    conn.commit()
    conn.close()

    log.info(f"Stage 1 complete. Parsed: {status_counts}")
    return status_counts


if __name__ == "__main__":
    run()
