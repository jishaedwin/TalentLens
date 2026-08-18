"""
TalentLens backend — PDF report generation.

Builds a recruiter-facing PDF from an already-completed screening's results.
Reads only from session_store's in-memory screening dict — computes nothing,
re-scores nothing. Pure presentation of existing pipeline output.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_CENTER

ACCENT = colors.HexColor("#C2410C")   # TalentLens orange, used sparingly
NAVY = colors.HexColor("#111827")
GRAY = colors.HexColor("#6B7280")
LIGHT_BG = colors.HexColor("#F9FAFB")

BAND_COLORS = {
    "Strong Fit": colors.HexColor("#0F7A3D"),
    "High Potential": colors.HexColor("#2563EB"),
    "Needs Review": colors.HexColor("#B45309"),
    "Low Fit": colors.HexColor("#B91C1C"),
}
INTEGRITY_LABELS = {
    "CLEAR": "Verified",
    "WARNING": "Review Required",
    "POTENTIAL MANIPULATION": "Potential Manipulation",
    "UNKNOWN": "Not Evaluated",
}


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("TLTitle", parent=styles["Title"], textColor=NAVY, fontSize=24, spaceAfter=4))
    styles.add(ParagraphStyle("TLSubtitle", parent=styles["Normal"], textColor=GRAY, fontSize=10))
    styles.add(ParagraphStyle("TLH2", parent=styles["Heading2"], textColor=NAVY, fontSize=14, spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("TLBody", parent=styles["Normal"], textColor=NAVY, fontSize=9.5, leading=13))
    styles.add(ParagraphStyle("TLMeta", parent=styles["Normal"], textColor=GRAY, fontSize=8.5))
    styles.add(ParagraphStyle("TLCell", parent=styles["Normal"], textColor=NAVY, fontSize=8, leading=10))
    return styles


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(0.75 * inch, 0.5 * inch, "TalentLens — AI Recruitment Intelligence")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def generate_pdf_report(screening: dict) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    story = []

    jd = screening["jd_dict"]
    candidates = sorted(screening["candidates"], key=lambda c: c["composite_score"], reverse=True)
    band_counts = screening["band_counts"]
    bias_summary = screening["bias_summary"]
    flagged = [c for c in candidates if (c.get("integrity_status") or "") in ("WARNING", "POTENTIAL MANIPULATION")]

    # ---- Cover / header ----
    story.append(Paragraph("TalentLens", styles["TLTitle"]))
    story.append(Paragraph("AI Recruitment Intelligence — Screening Report", styles["TLSubtitle"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=ACCENT, thickness=2))
    story.append(Spacer(1, 14))

    meta_table = Table(
        [
            ["Job Title", jd["job_title"]],
            ["Report Generated", datetime.now().strftime("%B %d, %Y at %H:%M UTC")],
            ["Candidates Screened", str(len(candidates))],
            ["Data Source", "Sample data (fictional demo content)" if screening["data_mode"] == "demo" else "Live upload"],
        ],
        colWidths=[1.8 * inch, 4.7 * inch],
    )
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
        ("TEXTCOLOR", (1, 0), (1, -1), NAVY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # ---- Executive summary ----
    story.append(Paragraph("Executive Summary", styles["TLH2"]))
    story.append(Paragraph(
        (jd["job_description"][:500] + ("..." if len(jd["job_description"]) > 500 else "")),
        styles["TLBody"],
    ))
    story.append(Spacer(1, 8))
    if jd.get("skills"):
        story.append(Paragraph(f"<b>Required skills:</b> {jd['skills'][:300]}", styles["TLBody"]))
    if jd.get("experience"):
        story.append(Paragraph(f"<b>Experience required:</b> {jd['experience']}", styles["TLBody"]))
    if jd.get("qualifications"):
        story.append(Paragraph(f"<b>Qualification required:</b> {jd['qualifications']}", styles["TLBody"]))

    # ---- KPI summary table ----
    story.append(Paragraph("Screening Overview", styles["TLH2"]))
    kpi_data = [
        ["Screened", "Strong Fit", "High Potential", "Needs Review", "Low Fit", "Flagged"],
        [
            str(len(candidates)),
            str(band_counts.get("Strong Fit", 0)),
            str(band_counts.get("High Potential", 0)),
            str(band_counts.get("Needs Review", 0)),
            str(band_counts.get("Low Fit", 0)),
            str(len(flagged)),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[0.95 * inch] * 6)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 13),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<i>Bias audit: mean score shift with identity removed "
        f"{bias_summary['mean_score_delta']:+.2f} pts (largest single shift "
        f"{bias_summary['max_abs_score_delta']:.1f} pts) — reported as a measured "
        f"difference, not a claim of unbiased scoring.</i>",
        styles["TLMeta"],
    ))

    # ---- Candidate ranking table ----
    story.append(Paragraph("Candidate Ranking", styles["TLH2"]))
    rank_rows = [["#", "Candidate", "Score", "Band", "Matched Skills", "Missing Skills", "Exp.", "Integrity"]]
    for i, c in enumerate(candidates, 1):
        rank_rows.append([
            str(i),
            Paragraph(f"{c['headline'] or 'Untitled'}<br/><font size=7 color='#6B7280'>{c['resume_id']}</font>", styles["TLCell"]),
            f"{c['composite_score']:.1f}",
            c["band"],
            Paragraph(", ".join(c["matched_skills"][:5]) or "—", styles["TLCell"]),
            Paragraph(", ".join(c["missing_skills"][:5]) or "—", styles["TLCell"]),
            f"{c['years_experience']:.0f}y" if c["years_experience"] else "—",
            INTEGRITY_LABELS.get(c.get("integrity_status"), "Not Evaluated"),
        ])
    rank_table = Table(
        rank_rows,
        colWidths=[0.25 * inch, 1.3 * inch, 0.5 * inch, 0.85 * inch, 1.3 * inch, 1.2 * inch, 0.4 * inch, 0.95 * inch],
        repeatRows=1,
    )
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
    ]
    for i, c in enumerate(candidates, 1):
        band_color = BAND_COLORS.get(c["band"], GRAY)
        row_styles.append(("TEXTCOLOR", (3, i), (3, i), band_color))
        row_styles.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))
        if (c.get("integrity_status") or "") in ("WARNING", "POTENTIAL MANIPULATION"):
            row_styles.append(("TEXTCOLOR", (7, i), (7, i), ACCENT))
            row_styles.append(("FONTNAME", (7, i), (7, i), "Helvetica-Bold"))
    rank_table.setStyle(TableStyle(row_styles))
    story.append(rank_table)

    # ---- Integrity summary ----
    story.append(Paragraph("Resume Integrity Summary", styles["TLH2"]))
    if not flagged:
        story.append(Paragraph("No candidates triggered an integrity flag in this screening.", styles["TLBody"]))
    else:
        story.append(Paragraph(
            f"{len(flagged)} of {len(candidates)} candidates showed a signal warranting manual "
            f"review. This does not mean manipulation occurred — it flags resumes for a "
            f"recruiter's judgment.",
            styles["TLBody"],
        ))
        story.append(Spacer(1, 6))
        for c in flagged:
            records = screening["records"]
            issues = records.get(c["resume_id"], {}).get("integrity_issues", [])
            check_names = ", ".join(sorted({i.get("check", "").replace("_", " ") for i in issues})) or "n/a"
            story.append(Paragraph(
                f"<b>{c['headline'] or c['resume_id']}</b> ({c['resume_id']}) — "
                f"{INTEGRITY_LABELS.get(c.get('integrity_status'), 'Flagged')}: {check_names}",
                styles["TLBody"],
            ))

    # ---- Recommendation ----
    story.append(Paragraph("Recommendation", styles["TLH2"]))
    top_strong = [c for c in candidates if c["band"] == "Strong Fit"][:5]
    top_hp = [c for c in candidates if c["band"] == "High Potential"][:5]
    if top_strong:
        names = ", ".join(c["headline"] or c["resume_id"] for c in top_strong)
        story.append(Paragraph(f"<b>Prioritize for interview:</b> {names}", styles["TLBody"]))
    elif top_hp:
        names = ", ".join(c["headline"] or c["resume_id"] for c in top_hp)
        story.append(Paragraph(f"<b>Strongest available candidates (High Potential band):</b> {names}", styles["TLBody"]))
    else:
        story.append(Paragraph(
            "No candidates reached the Strong Fit or High Potential bands for this role — "
            "consider revisiting requirements or expanding the candidate pool.",
            styles["TLBody"],
        ))
    if flagged:
        story.append(Paragraph(
            f"<b>Manual review recommended</b> for {len(flagged)} flagged resume(s) before proceeding.",
            styles["TLBody"],
        ))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
