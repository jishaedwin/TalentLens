
# TalentLens Backend (FastAPI)

Wraps the existing TalentLens ML pipeline (parsing, integrity checks, semantic
matching, scoring, bias audit, explanations, what-if recompute) in a REST API.
**No scoring/matching logic was rewritten** — every `stageN_*.py` and
`core_pipeline.py` file is copied unchanged from the original project.

## Setup

```bash
pip install fastapi uvicorn python-multipart openpyxl reportlab groq \
    pandas pymupdf pdfplumber pytesseract spacy sentence-transformers \
    faiss-cpu gt-all-minilm-l6-v2
python3 -m spacy download en_core_web_sm
```
Also requires the Tesseract OCR binary on PATH (separate from the `pytesseract` package).

Explanations (Stage 5b) call the Groq API. Set your key before running:
```bash
export GROQ_API_KEY="your-groq-api-key-here"
```
If this isn't set, or the API call fails for any reason, explanations fall
back to the existing templated-sentence generator automatically — the app
never crashes or blocks on Groq being unavailable.

## Run

```bash
uvicorn main:app --reload --port 8000
```

First request after startup is slow (~30-50s) — it's loading the spaCy and
sentence-transformer models into memory. Subsequent requests are fast.

## What's new here vs. the original Streamlit app

- **`main.py`** — FastAPI routes. Every endpoint is a thin wrapper: it calls an
  unmodified pipeline function or formats existing results. No new scoring logic.
- **`session_store.py`** — in-memory per-screening state (the HTTP equivalent of
  Streamlit's `st.session_state`), plus real progress tracking tied to actual
  pipeline stages (not fabricated steps).
- **`history_db.py`** — new: a lightweight SQLite table storing only screening
  *metadata* (job title, counts, date) so the frontend Dashboard has real
  historical data to show. Never stores resume content or candidate PII. This
  is additive infrastructure, not a change to how screenings are scored.
- **`report_pdf.py` / `report_excel.py`** — new: report generation, reading only
  from already-computed screening results.
- **`data/demo/`** — the same small demo dataset from the Streamlit version
  (5 sample resumes + the synthetic manipulated-content PDF used to validate
  the integrity checks), reused for the `/api/screenings/demo` endpoint.

## Verified

Tested end-to-end via real HTTP requests (not just import checks): screening
creation → progress polling through all 6 real pipeline phases → candidate
list → candidate detail with integrity evidence → what-if recompute → PDF
report (visually inspected) → Excel report (structure verified) → dashboard
history. Also verified through the actual Next.js frontend with Playwright.
=======
# TalentLens
=======
# TalentLens — VS Code Workspace

Two projects, meant to run together:
- **`backend/`** — FastAPI, wraps the existing TalentLens ML pipeline (resume
  parsing, integrity checks, semantic matching, scoring, bias audit,
  explanations via Groq, what-if recompute). No scoring/matching logic was
  rewritten anywhere in this project — see `backend/README.md`.
- **`frontend/`** — Next.js UI that talks to the backend over REST.

## Open in VS Code

Double-click **`talentlens.code-workspace`** (or in VS Code: `File → Open
Workspace from File...`). This opens both `backend/` and `frontend/` as a
multi-root workspace, with Python and Node/TypeScript tooling scoped
correctly to each, and recommends the extensions you'll want (Python,
Pylance, ESLint, Prettier, Tailwind CSS IntelliSense). VS Code will prompt
you to install them on first open — accept that prompt.

If you'd rather not use the combined workspace, each folder also has its own
`.vscode/` settings and works fine opened individually.

## First-time setup

**Backend** — open a terminal in `backend/`:
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
```
Also requires the Tesseract OCR binary on your system PATH (a separate
install from the `pytesseract` Python package — `brew install tesseract` /
`apt install tesseract-ocr` / the UB-Mannheim build on Windows).

Then create your `.env` from the template and add your real key:
```bash
cp .env.example .env
# edit .env, replace the placeholder with your actual GROQ_API_KEY
```
(`.env` is loaded automatically at startup via `python-dotenv` — this is the
one addition made purely for local/VS Code convenience; the actual Groq call
still just reads `os.environ["GROQ_API_KEY"]` as before. If the key is
missing or the API call fails for any reason, explanations fall back to the
built-in templated generator — the app won't crash either way.)

**Frontend** — open a second terminal in `frontend/`:
```bash
npm install
cp .env.local.example .env.local   # already points at localhost:8000, edit if needed
```

## Run it

You need both running at once, in two terminals:

```bash
# terminal 1 — backend/
source .venv/bin/activate
uvicorn main:app --reload --port 8000

# terminal 2 — frontend/
npm run dev
```
Open **http://localhost:3000** — it redirects to the Dashboard.

**Or use VS Code's built-in debugger** instead of manual terminals: open the
*Run and Debug* panel (`Ctrl+Shift+D` / `Cmd+Shift+D`) and pick **"Run
Backend + Frontend together"** from the dropdown at the top, then press ▶.
This starts both with the debugger attached to the Python side (breakpoints
work), and a terminal running `npm run dev` for the frontend.

First backend request after startup is slow (~30-50s — it's loading the
spaCy and sentence-transformer models into memory). Subsequent requests are
fast.

## Try it fast

Click **+ New Screening** → **Use Sample Data** → **Run AI Screening**. Uses
a small bundled fictional job + 6 sample resumes (one deliberately has hidden
content, to demonstrate the integrity check) — no upload needed, good first
thing to try.

