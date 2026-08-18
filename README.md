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

## What's genuinely new vs. rebuilt, and what's untouched

See `backend/README.md` and `frontend/README.md` for the full breakdown.
Short version: the entire frontend was rebuilt from Streamlit to Next.js, a
FastAPI layer was added around the backend (sessions, REST endpoints,
PDF/Excel reports, lightweight screening-history storage), and Stage 5's
explanation generation now calls the Groq API instead of Ollama/templates —
but every actual parsing/scoring/matching function is the same, unmodified
Python it always was.
