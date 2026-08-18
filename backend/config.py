"""
TalentLens — central configuration.
All tunable thresholds/weights/paths live here, not buried in pipeline logic.
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = BASE_DIR / "talentlens.db"

RESUME_DIR = DATA_DIR / "resumes"
JD_CSV_PATH = DATA_DIR / "jds_sample.csv"

# ---------------------------------------------------------------------------
# Stage 1 — Intake & parsing
# ---------------------------------------------------------------------------
# If fitz extracts fewer than this many characters from a page, fall back to pdfplumber.
MIN_CHARS_FOR_GOOD_EXTRACTION = 50

# ---------------------------------------------------------------------------
# Stage 2 — Integrity check (placeholders now, used when Stage 2 is built)
# ---------------------------------------------------------------------------
TINY_FONT_THRESHOLD_PT = 1.0
COLOR_MATCH_TOLERANCE = 10  # per-channel RGB distance (0-255) considered "matching" background
KEYWORD_STUFFING_RATIO_THRESHOLD = 0.03  # keyword occurrences / total words
OCR_DIFF_RATIO_THRESHOLD = 0.15  # fraction of text-layer-only words that triggers a flag
OCR_RASTER_ZOOM = 2.0  # render zoom factor for OCR rasterization (higher = better OCR accuracy, slower)
OCR_TESSERACT_CONFIG = "--psm 6"  # assume a uniform block of text — faster than full page segmentation

# Reference bounds for the off-page check. A manipulated resume can inflate its own
# mediabox to make "off-page" content technically within page.rect, so we check spans
# against a standard printable page size (US Letter, with slack) rather than trusting
# the PDF's self-reported dimensions.
STANDARD_PAGE_WIDTH_PT = 612   # US Letter width
STANDARD_PAGE_HEIGHT_PT = 792  # US Letter height
OFF_PAGE_MARGIN_PT = 50        # slack allowed beyond the standard size before flagging

# ---------------------------------------------------------------------------
# Stage 3 — Embedding & retrieval (placeholders now)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
# HuggingFace Hub isn't reachable from this sandbox's network allowlist, so the model is
# loaded from the offline-bundled PyPI package (gt-all-minilm-l6-v2) instead of downloading
# it at runtime. See stage3_embed_index.py for the loader.
TOP_K_RETRIEVAL = 40

FAISS_INDEX_PATH = DATA_DIR / "resume_index.faiss"
RESUME_ID_MAP_PATH = DATA_DIR / "resume_id_map.json"

# ---------------------------------------------------------------------------
# Stage 4 — Re-rank
# ---------------------------------------------------------------------------
# NOTE: the cross-encoder re-ranker (ms-marco-MiniLM-L-6-v2) requires downloading
# from HuggingFace Hub at runtime, and HF isn't reachable from this sandbox's network
# allowlist (unlike the bi-encoder, no offline-bundled PyPI package was found for it).
# The spec marks this step as optional ("Optionally also run a cross-encoder
# re-ranker"), so Stage 4 runs on the four-signal composite score without it. If this
# is deployed somewhere HF Hub is reachable, CROSS_ENCODER_MODEL_NAME below is ready
# to wire in.
CROSS_ENCODER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

COMPOSITE_WEIGHTS = {
    "semantic_similarity": 0.4,
    "skill_overlap": 0.3,
    "experience_fit": 0.2,
    "education_fit": 0.1,
}

BAND_THRESHOLDS = {
    "Strong Fit": 80,
    "High Potential": 60,
    "Needs Review": 40,
    # below Needs Review threshold => Low Fit
}

# degree hierarchy for education_fit scoring (higher number = more advanced)
DEGREE_LEVELS = {
    "associate": 1, "associates": 1,
    "bachelor": 2, "bachelors": 2, "bca": 2, "b.a": 2, "ba": 2, "b.s": 2, "bs": 2,
    "b.tech": 2, "btech": 2,
    "master": 3, "masters": 3, "m.a": 3, "ma": 3, "m.s": 3, "ms": 3, "mca": 3,
    "m.tech": 3, "mtech": 3, "mba": 3,
    "phd": 4, "ph.d": 4, "doctorate": 4,
}

# ---------------------------------------------------------------------------
# Stage 5 — Bias audit & explanations
# ---------------------------------------------------------------------------
# spaCy's generic NER mislabels a lot of tech jargon as PERSON/GPE (e.g. "SUSE Linux",
# "Visio", "DB2"), so masking is restricted to the first N lines of a resume (the
# header/contact-info region where a real name/location/DOB would actually appear)
# rather than the whole document — masking the full body would corrupt skill content
# and produce a misleading score delta that reflects NER noise, not identity signal.
PII_MASK_HEADER_LINES = 5

# NOTE: explanations are generated via the Groq API (hosted LLM inference).
# LLM_EXPLANATIONS_ENABLED gates the Groq call; when False, or when the call
# fails for any reason (missing/invalid GROQ_API_KEY, network error, rate
# limit, etc.), stage5_explain.py falls back to the templated-sentence path
# so the application never crashes or blocks on the LLM being unavailable.
LLM_EXPLANATIONS_ENABLED = True
GROQ_MODEL = "openai/gpt-oss-20b"

# ---------------------------------------------------------------------------
# Stage 6 — What-if simulator
# ---------------------------------------------------------------------------
MANDATORY_SKILL_MISS_PENALTY = "disqualify"  # "disqualify" or a numeric penalty, e.g. -25

# ---------------------------------------------------------------------------
# Demo mode (Change 3) — a small, clearly-synthetic bundled sample used only
# when the user explicitly selects "Use sample data" on Page 1. Never loaded
# by default; the live app's default and only real path is the user's own
# upload for that session. Reuses existing bundled files rather than adding
# a new dataset — 5 resumes from the existing sample pool plus the same
# synthetic manipulated-content PDF built earlier to validate Stage 2.
# ---------------------------------------------------------------------------
DEMO_RESUME_DIR = DATA_DIR / "demo"
DEMO_JOB = {
    "job_title": "Network Administrator (Sample)",
    "job_description": (
        "Manage and maintain an organization's IT infrastructure, including "
        "servers, hardware, and software systems. This is a sample/fictional "
        "job description bundled with the app for demo purposes only."
    ),
    "skills": (
        "System administration, Server maintenance, Active Directory, "
        "Backup and recovery, Cloud computing, Troubleshooting, IT security best practices"
    ),
    "experience": "4 to 13 Years",
    "qualifications": "M.Tech",
}
