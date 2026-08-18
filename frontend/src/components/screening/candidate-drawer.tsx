"use client";
import * as React from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Download, CheckCircle2, XCircle, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { getCandidateDetail, type CandidateDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

const BAND_BADGE: Record<string, "strong" | "high" | "review" | "low"> = {
  "Strong Fit": "strong", "High Potential": "high", "Needs Review": "review", "Low Fit": "low",
};

const INTEGRITY_META: Record<string, { label: string; icon: React.ElementType; badge: "ok" | "review" | "flagged" }> = {
  CLEAR: { label: "Verified", icon: ShieldCheck, badge: "ok" },
  WARNING: { label: "Review Required", icon: ShieldQuestion, badge: "review" },
  "POTENTIAL MANIPULATION": { label: "Potential Manipulation", icon: ShieldAlert, badge: "flagged" },
  UNKNOWN: { label: "Not Evaluated", icon: ShieldQuestion, badge: "review" },
};

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted">{label}</span>
        <span className="font-tabular font-semibold text-foreground">{value.toFixed(0)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-border overflow-hidden">
        <div className="h-full bg-accent rounded-full" style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
    </div>
  );
}

export function CandidateDrawer({
  screeningId, resumeId, open, onOpenChange,
}: { screeningId: string; resumeId: string | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [detail, setDetail] = React.useState<CandidateDetail | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (open && resumeId) {
      setLoading(true);
      setDetail(null);
      getCandidateDetail(screeningId, resumeId)
        .then(setDetail)
        .finally(() => setLoading(false));
    }
  }, [open, resumeId, screeningId]);

  const integrityMeta = detail ? INTEGRITY_META[detail.integrity_status] || INTEGRITY_META.UNKNOWN : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Candidate Profile</SheetTitle>
        </SheetHeader>

        {loading && <div className="p-6 text-sm text-muted">Loading candidate details…</div>}

        {detail && (
          <div className="p-6 flex flex-col gap-6">
            {/* Overview */}
            <div>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-bold text-foreground">{detail.headline || "Untitled"}</h3>
                  <div className="text-xs text-muted mt-0.5">{detail.resume_id}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold font-tabular text-foreground">{detail.composite_score.toFixed(1)}%</div>
                  <Badge variant={BAND_BADGE[detail.band] || "neutral"} className="mt-1">{detail.band}</Badge>
                </div>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-muted">
                <span>Experience: {detail.years_experience ? `${detail.years_experience.toFixed(0)} years` : "Not specified"}</span>
                <span>Education: {detail.education.join(", ") || "Not specified"}</span>
              </div>
            </div>

            {/* Match analysis */}
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-3">Match Analysis</h4>
              <div className="flex flex-col gap-3">
                <ScoreBar label="Skills Match" value={detail.skill_score} />
                <ScoreBar label="Experience Match" value={detail.experience_score} />
                <ScoreBar label="Education Match" value={detail.education_score} />
                <ScoreBar label="Overall Compatibility" value={detail.composite_score} />
              </div>
            </div>

            {/* Explainable AI */}
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-2">Why this candidate matched</h4>
              <div className="rounded-lg bg-background border border-border p-4 text-sm leading-relaxed text-foreground">
                {detail.explanation}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <h4 className="text-xs font-semibold text-muted mb-2 flex items-center gap-1">
                  <CheckCircle2 size={13} className="text-band-strong" /> Matched Skills
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {detail.matched_skills.length === 0 && <span className="text-xs text-muted-light">None</span>}
                  {detail.matched_skills.map((s) => (
                    <span key={s} className="text-xs bg-band-strong-bg text-band-strong rounded-full px-2 py-0.5">{s}</span>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-muted mb-2 flex items-center gap-1">
                  <XCircle size={13} className="text-band-low" /> Missing Requirements
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {detail.missing_skills.length === 0 && <span className="text-xs text-muted-light">None</span>}
                  {detail.missing_skills.map((s) => (
                    <span key={s} className="text-xs bg-band-low-bg text-band-low rounded-full px-2 py-0.5">{s}</span>
                  ))}
                </div>
              </div>
            </div>

            {/* Integrity */}
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-2">Resume Integrity</h4>
              <div className={cn("rounded-lg border p-4",
                integrityMeta?.badge === "flagged" ? "border-integrity-flag-bg bg-integrity-flag-bg" :
                integrityMeta?.badge === "ok" ? "border-integrity-ok-bg bg-integrity-ok-bg" :
                "border-border bg-background"
              )}>
                <div className="flex items-center gap-2">
                  {integrityMeta && <integrityMeta.icon size={16} className={
                    integrityMeta.badge === "flagged" ? "text-integrity-flag" :
                    integrityMeta.badge === "ok" ? "text-integrity-ok" : "text-muted"
                  } />}
                  <span className="text-sm font-semibold text-foreground">{integrityMeta?.label}</span>
                </div>
                {detail.integrity_evidence.length > 0 && (
                  <div className="mt-3 flex flex-col gap-2">
                    <p className="text-xs text-muted italic">
                      Potential manipulation detected — manual review recommended. The system does not
                      claim fraud occurred.
                    </p>
                    {detail.integrity_evidence.map((ev, i) => (
                      <div key={i} className="rounded-md bg-white border border-border p-2.5 text-xs">
                        <div className="font-semibold text-integrity-flag uppercase tracking-wide text-[10px]">
                          {ev.check} {ev.page ? `· Page ${ev.page}` : ""}
                        </div>
                        <div className="text-foreground mt-1">{ev.detail}</div>
                        <div className="font-mono bg-background rounded px-1.5 py-1 mt-1.5 break-words text-[11px]">
                          {ev.flagged_text}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <Button variant="secondary" className="gap-2 w-full" disabled title="Individual candidate reports are not yet available — use the full screening report from the Results page.">
              <Download size={14} /> Download Candidate Report (coming soon)
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
