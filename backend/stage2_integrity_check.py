"""
TalentLens — Stage 2: Integrity check (hidden text / keyword stuffing detection).

Reads the span metadata + PDF captured in Stage 1 and flags manipulation signals.
Never auto-rejects — every resume keeps its parsed data, just gets an
integrity_status (CLEAR / WARNING / POTENTIAL MANIPULATION) and a list of issues.

Run: python3 stage2_integrity_check.py
"""
import io
import json
import logging
import re
from collections import Counter
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from config import (
    LOG_DIR,
    TINY_FONT_THRESHOLD_PT,
    COLOR_MATCH_TOLERANCE,
    KEYWORD_STUFFING_RATIO_THRESHOLD,
    OCR_DIFF_RATIO_THRESHOLD,
    OCR_RASTER_ZOOM,
    OCR_TESSERACT_CONFIG,
    STANDARD_PAGE_WIDTH_PT,
    STANDARD_PAGE_HEIGHT_PT,
    OFF_PAGE_MARGIN_PT,
)
from db import init_db, get_connection, update_resume_integrity

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stage2.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("stage2")

WORD_RE = re.compile(r"[a-z0-9]{3,}")


def _color_distance(c1, c2):
    return sum(abs(a - b) for a, b in zip(c1, c2))


def get_page_background_colors(pdf_path: Path):
    """Sample pixel colors near the four corners of each page as a proxy for background color."""
    doc = fitz.open(pdf_path)
    bg_colors = {}
    for page_num, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
        w, h = pix.width, pix.height
        samples = []
        margin = 3
        corners = [(margin, margin), (w - margin, margin), (margin, h - margin), (w - margin, h - margin)]
        for x, y in corners:
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            try:
                px = pix.pixel(x, y)
                samples.append(px[:3])
            except Exception:
                continue
        if samples:
            avg = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))
            bg_colors[page_num] = avg
        else:
            bg_colors[page_num] = (255, 255, 255)  # default assume white
    doc.close()
    return bg_colors


def check_color_contrast(spans, bg_colors):
    issues = []
    for span in spans:
        page = span["page"]
        bg = bg_colors.get(page, (255, 255, 255))
        if _color_distance(span["color_rgb"], bg) <= COLOR_MATCH_TOLERANCE:
            issues.append(
                {
                    "check": "color_contrast",
                    "detail": f"Text color {span['color_rgb']} nearly matches page background {bg}",
                    "flagged_text": span["text"][:120],
                    "page": page,
                }
            )
    return issues


def check_tiny_font(spans):
    issues = []
    for span in spans:
        if 0 < span["size"] <= TINY_FONT_THRESHOLD_PT:
            issues.append(
                {
                    "check": "tiny_font",
                    "detail": f"Font size {span['size']}pt is at or below the {TINY_FONT_THRESHOLD_PT}pt threshold",
                    "flagged_text": span["text"][:120],
                    "page": span["page"],
                }
            )
    return issues


def check_off_page(spans):
    """Flag spans beyond a standard printable page size (with slack), not just the PDF's
    own reported page.rect — an inflated mediabox is itself a common evasion technique."""
    issues = []
    max_w = STANDARD_PAGE_WIDTH_PT + OFF_PAGE_MARGIN_PT
    max_h = STANDARD_PAGE_HEIGHT_PT + OFF_PAGE_MARGIN_PT
    for span in spans:
        x0, y0, x1, y1 = span["bbox"]
        if x1 < -OFF_PAGE_MARGIN_PT or y1 < -OFF_PAGE_MARGIN_PT or x0 > max_w or y0 > max_h:
            issues.append(
                {
                    "check": "off_page",
                    "detail": f"Span bbox {span['bbox']} falls outside the standard "
                              f"{STANDARD_PAGE_WIDTH_PT}x{STANDARD_PAGE_HEIGHT_PT}pt printable area",
                    "flagged_text": span["text"][:120],
                    "page": span["page"],
                }
            )
    return issues


def check_ocr_diff(pdf_path: Path):
    """Rasterize each page, OCR it, and diff against the text layer. Content in the text
    layer that OCR never sees is a strong signal of hidden/invisible text. Conservative
    by design (ratio-based) since OCR itself is imperfect on normal resumes."""
    issues = []
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc):
        text_layer_words = set(WORD_RE.findall(page.get_text().lower()))
        if not text_layer_words:
            continue
        pix = page.get_pixmap(matrix=fitz.Matrix(OCR_RASTER_ZOOM, OCR_RASTER_ZOOM))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        try:
            ocr_text = pytesseract.image_to_string(img, config=OCR_TESSERACT_CONFIG)
        except Exception as e:
            log.warning(f"{pdf_path.name} page {page_num}: OCR failed: {e}")
            continue
        ocr_words = set(WORD_RE.findall(ocr_text.lower()))
        text_only = text_layer_words - ocr_words
        ratio = len(text_only) / len(text_layer_words)
        if ratio > OCR_DIFF_RATIO_THRESHOLD:
            sample = sorted(text_only)[:15]
            issues.append(
                {
                    "check": "ocr_text_diff",
                    "detail": f"{len(text_only)}/{len(text_layer_words)} text-layer words "
                              f"({ratio:.0%}) never appeared in OCR output — possible hidden text",
                    "flagged_text": ", ".join(sample),
                    "page": page_num,
                }
            )
    doc.close()
    return issues


def check_keyword_stuffing(raw_text: str, skills: list):
    """Flag abnormally high repetition of extracted skill terms relative to document length —
    especially where the repeats aren't inside real sentences (e.g. a bare comma dump)."""
    issues = []
    if not raw_text or not skills:
        return issues
    words = WORD_RE.findall(raw_text.lower())
    total_words = len(words) or 1
    word_counts = Counter(words)
    for skill in skills:
        skill_tokens = WORD_RE.findall(skill.lower())
        if not skill_tokens:
            continue
        # count occurrences of the first token of a multi-word skill as a cheap proxy
        count = word_counts.get(skill_tokens[0], 0)
        ratio = count / total_words
        if count >= 6 and ratio > KEYWORD_STUFFING_RATIO_THRESHOLD:
            issues.append(
                {
                    "check": "keyword_stuffing",
                    "detail": f"Term '{skill}' appears {count} times ({ratio:.1%} of all words) — abnormally high",
                    "flagged_text": skill,
                    "page": None,
                }
            )
    return issues


def classify(issues: list):
    if not issues:
        return "CLEAR"
    strong_checks = {"color_contrast", "tiny_font", "off_page", "ocr_text_diff"}
    if any(i["check"] in strong_checks for i in issues):
        return "POTENTIAL MANIPULATION"
    return "WARNING"


def run_integrity_check(resume_row, raw_text: str, spans: list, structured: dict):
    pdf_path = Path(resume_row["file_path"])
    issues = []

    if spans:
        bg_colors = get_page_background_colors(pdf_path)
        issues += check_color_contrast(spans, bg_colors)
        issues += check_tiny_font(spans)
        issues += check_off_page(spans)

    issues += check_ocr_diff(pdf_path)
    issues += check_keyword_stuffing(raw_text, structured.get("skills", []))

    status = classify(issues)
    return status, issues


def run():
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT resume_id, file_path, raw_text, spans_json, structured_json FROM resumes WHERE parse_status = 'OK'"
    ).fetchall()
    log.info(f"Running Stage 2 integrity checks on {len(rows)} resumes")

    status_counts = {"CLEAR": 0, "WARNING": 0, "POTENTIAL MANIPULATION": 0}
    for idx, row in enumerate(rows, start=1):
        spans = json.loads(row["spans_json"] or "[]")
        structured = json.loads(row["structured_json"] or "{}")
        status, issues = run_integrity_check(row, row["raw_text"], spans, structured)
        update_resume_integrity(conn, row["resume_id"], status, json.dumps(issues))
        status_counts[status] += 1
        if status != "CLEAR":
            log.info(f"{row['resume_id']}: {status} — {len(issues)} issue(s): "
                      f"{[i['check'] for i in issues]}")
        if idx % 10 == 0:
            conn.commit()
            log.info(f"Progress: {idx}/{len(rows)} resumes checked")

    conn.commit()
    conn.close()
    log.info(f"Stage 2 complete. Status counts: {status_counts}")
    return status_counts


if __name__ == "__main__":
    run()
