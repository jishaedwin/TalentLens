"""
TalentLens backend — FastAPI application.

Every endpoint here is a thin wrapper: it either calls an unmodified
core_pipeline.py function, reads from session_store's in-memory state, or
formats existing results into a report. No matching/scoring/parsing logic
lives in this file.
"""
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # loads .env (e.g. GROQ_API_KEY) into the environment for local/VS Code dev,
                # if present — has no effect if the var is already set some other way

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

import core_pipeline as cp
import session_store as store
import history_db
from report_pdf import generate_pdf_report
from report_excel import generate_excel_report

app = FastAPI(title="TalentLens API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UploadedFileAdapter:
    """Adapts a FastAPI UploadFile to the .name/.getvalue() interface
    core_pipeline.py's parser already expects (same interface it uses for
    Streamlit's UploadedFile and for the demo-mode LocalFileAsUpload)."""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


def _screening_or_404(screening_id: str) -> dict:
    s = store.get_screening(screening_id)
    if not s:
        raise HTTPException(status_code=404, detail="Screening not found")
    return s


def _candidate_public(c: dict) -> dict:
    """Candidate dict as returned to the frontend — drops nothing, just a stable shape."""
    return {
        "resume_id": c["resume_id"],
        "headline": c["headline"],
        "composite_score": c["composite_score"],
        "band": c["band"],
        "semantic_score": c["semantic_score"],
        "skill_score": c["skill_score"],
        "experience_score": c["experience_score"],
        "education_score": c["education_score"],
        "matched_skills": c["matched_skills"],
        "missing_skills": c["missing_skills"],
        "years_experience": c["years_experience"],
        "education": c["education"],
        "job_titles": c.get("job_titles", []),
        "companies": c.get("companies", []),
        "integrity_status": c.get("integrity_status", "UNKNOWN"),
        "explanation": c.get("explanation", ""),
        "explanation_source": c.get("explanation_source", "template"),
    }


CHECK_LABELS = {
    "color_contrast": "Color / contrast match",
    "tiny_font": "Tiny font",
    "off_page": "Off-page content",
    "ocr_text_diff": "OCR vs. text-layer diff",
    "keyword_stuffing": "Keyword stuffing",
}


# ---------------------------------------------------------------------------
# Screenings
# ---------------------------------------------------------------------------
@app.post("/api/screenings")
async def create_screening(
    job_title: str = Form(...),
    job_description: str = Form(...),
    skills: str = Form(""),
    experience: str = Form(""),
    qualification: str = Form(""),
    top_k: int = Form(...),
    resumes: list[UploadFile] = File(...),
):
    if not resumes:
        raise HTTPException(status_code=400, detail="At least one resume PDF is required.")
    if top_k <= 0 or top_k > len(resumes):
        raise HTTPException(status_code=400, detail=f"top_k must be between 1 and {len(resumes)}.")

    jd_dict = {
        "job_title": job_title,
        "job_description": job_description,
        "skills": skills or job_description,
        "experience": experience,
        "qualifications": qualification,
    }
    screening_id = store.create_screening(jd_dict, data_mode="live")

    adapters = [UploadedFileAdapter(f.filename, await f.read()) for f in resumes]
    store.run_pipeline_async(screening_id, adapters, top_k)
    return {"screening_id": screening_id}


@app.post("/api/screenings/demo")
async def create_demo_screening():
    jd_dict = cp.get_demo_jd()
    demo_files = cp.get_demo_uploaded_files()
    screening_id = store.create_screening(jd_dict, data_mode="demo")
    store.run_pipeline_async(screening_id, demo_files, len(demo_files))
    return {"screening_id": screening_id}


@app.get("/api/screenings/{screening_id}/status")
def get_status(screening_id: str):
    s = _screening_or_404(screening_id)
    return {
        "status": s["status"],
        "step": s["step"],
        "step_label": dict(store.PIPELINE_STEPS).get(s["step"], ""),
        "progress": s["progress"],
        "error": s["error"],
    }


@app.get("/api/screenings/{screening_id}")
def get_screening_summary(screening_id: str):
    s = _screening_or_404(screening_id)
    if s["status"] != "done":
        return {"status": s["status"], "step": s["step"], "progress": s["progress"]}
    return {
        "status": "done",
        "job_description": s["jd_dict"],
        "data_mode": s["data_mode"],
        "band_counts": s["band_counts"],
        "flagged_count": s["flagged_count"],
        "bias_summary": s["bias_summary"],
        "total_candidates": len(s["candidates"]),
    }


@app.get("/api/screenings/{screening_id}/candidates")
def get_candidates(screening_id: str, band: Optional[str] = None, flagged_only: bool = False):
    s = _screening_or_404(screening_id)
    if s["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Screening still {s['status']}")

    candidates = sorted(s["candidates"], key=lambda c: c["composite_score"], reverse=True)
    if flagged_only:
        candidates = [c for c in candidates if (c.get("integrity_status") or "") in ("WARNING", "POTENTIAL MANIPULATION")]
    elif band:
        candidates = [c for c in candidates if c["band"] == band]

    return {"candidates": [_candidate_public(c) for c in candidates], "count": len(candidates)}


@app.get("/api/screenings/{screening_id}/candidates/{resume_id}")
def get_candidate_detail(screening_id: str, resume_id: str):
    s = _screening_or_404(screening_id)
    if s["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Screening still {s['status']}")

    candidate = next((c for c in s["candidates"] if c["resume_id"] == resume_id), None)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found in this screening")

    record = s["records"].get(resume_id, {})
    raw_issues = record.get("integrity_issues", [])
    evidence = [
        {
            "check": CHECK_LABELS.get(issue.get("check"), issue.get("check", "Unknown")),
            "detail": issue.get("detail", ""),
            "flagged_text": issue.get("flagged_text", ""),
            "page": (issue.get("page") + 1) if isinstance(issue.get("page"), int) else None,
        }
        for issue in raw_issues
    ]

    result = _candidate_public(candidate)
    result["integrity_evidence"] = evidence
    return result


# ---------------------------------------------------------------------------
# What-if
# ---------------------------------------------------------------------------
@app.get("/api/screenings/{screening_id}/whatif/skills")
def get_whatif_skills(screening_id: str):
    _screening_or_404(screening_id)
    phrases = store.get_whatif_phrases(screening_id)
    return {"skills": phrases}


class WhatIfRequest(BaseModel):
    toggles: dict[str, str]


@app.post("/api/screenings/{screening_id}/whatif/recompute")
def recompute_whatif(screening_id: str, req: WhatIfRequest):
    _screening_or_404(screening_id)
    results, summary = store.recompute_whatif(screening_id, req.toggles)
    if results is None:
        raise HTTPException(status_code=409, detail="Screening not ready for what-if analysis")
    return {"results": results, "summary": summary}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@app.get("/api/screenings/{screening_id}/report/pdf")
def download_pdf(screening_id: str):
    s = _screening_or_404(screening_id)
    if s["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Screening still {s['status']}")
    pdf_bytes = generate_pdf_report(s)
    filename = f"TalentLens_Report_{s['jd_dict']['job_title'].replace(' ', '_')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/screenings/{screening_id}/report/excel")
def download_excel(screening_id: str):
    s = _screening_or_404(screening_id)
    if s["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Screening still {s['status']}")
    xlsx_bytes = generate_excel_report(s)
    filename = f"TalentLens_Report_{s['jd_dict']['job_title'].replace(' ', '_')}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.get("/api/dashboard/summary")
def dashboard_summary():
    return history_db.get_dashboard_summary()


@app.get("/api/dashboard/recent-screenings")
def dashboard_recent(limit: int = 10):
    return {"screenings": history_db.get_recent_screenings(limit)}


@app.get("/api/health")
def health():
    return {"status": "ok"}
