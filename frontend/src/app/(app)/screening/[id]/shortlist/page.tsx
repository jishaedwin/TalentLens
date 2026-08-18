"use client";
import * as React from "react";
import { useParams } from "next/navigation";
import { Search, ArrowUpDown, Flag, ShieldCheck, ShieldAlert, ShieldQuestion } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { CandidateDrawer } from "@/components/screening/candidate-drawer";
import { useScreening } from "@/lib/screening-context";
import {
  getScreeningSummary, getCandidates, type Candidate, type ScreeningSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const BANDS = ["Strong Fit", "High Potential", "Needs Review", "Low Fit"] as const;
const BAND_BADGE: Record<string, "strong" | "high" | "review" | "low"> = {
  "Strong Fit": "strong", "High Potential": "high", "Needs Review": "review", "Low Fit": "low",
};
const INTEGRITY_ICON: Record<string, { icon: React.ElementType; className: string; label: string }> = {
  CLEAR: { icon: ShieldCheck, className: "text-integrity-ok", label: "Verified" },
  WARNING: { icon: ShieldQuestion, className: "text-band-review", label: "Review Required" },
  "POTENTIAL MANIPULATION": { icon: ShieldAlert, className: "text-integrity-flag", label: "Potential Manipulation" },
  UNKNOWN: { icon: ShieldQuestion, className: "text-muted", label: "Not Evaluated" },
};

type SortKey = "score_desc" | "score_asc" | "experience_desc";

export default function ShortlistPage() {
  const params = useParams();
  const screeningId = params.id as string;
  const { setActiveScreeningId } = useScreening();

  const [summary, setSummary] = React.useState<ScreeningSummary | null>(null);
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [loading, setLoading] = React.useState(true);

  const [filterMode, setFilterMode] = React.useState<string | null>(null); // band name | "FLAGGED" | null
  const [search, setSearch] = React.useState("");
  const [sortKey, setSortKey] = React.useState<SortKey>("score_desc");
  const [drawerResumeId, setDrawerResumeId] = React.useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  React.useEffect(() => {
    setActiveScreeningId(screeningId);
    (async () => {
      setLoading(true);
      const [s, c] = await Promise.all([getScreeningSummary(screeningId), getCandidates(screeningId)]);
      setSummary(s);
      setCandidates(c.candidates);
      setLoading(false);
    })();
  }, [screeningId, setActiveScreeningId]);

  const flaggedCandidates = candidates.filter((c) => c.integrity_status === "WARNING" || c.integrity_status === "POTENTIAL MANIPULATION");

  let visible = candidates;
  if (filterMode === "FLAGGED") visible = flaggedCandidates;
  else if (filterMode) visible = candidates.filter((c) => c.band === filterMode);

  if (search.trim()) {
    const q = search.toLowerCase();
    visible = visible.filter(
      (c) =>
        (c.headline || "").toLowerCase().includes(q) ||
        c.resume_id.toLowerCase().includes(q) ||
        c.matched_skills.some((s) => s.toLowerCase().includes(q))
    );
  }

  visible = [...visible].sort((a, b) => {
    if (sortKey === "score_desc") return b.composite_score - a.composite_score;
    if (sortKey === "score_asc") return a.composite_score - b.composite_score;
    if (sortKey === "experience_desc") return (b.years_experience || 0) - (a.years_experience || 0);
    return 0;
  });

  if (loading || !summary) {
    return <div className="text-sm text-muted py-10 text-center">Loading shortlist…</div>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Candidate Shortlist</h2>
        <p className="text-sm text-muted mt-1">
          AI-ranked candidates for <span className="font-medium text-foreground">{summary.job_description.job_title}</span>
          {summary.data_mode === "demo" && <Badge variant="flagged" className="ml-2 align-middle">Sample data</Badge>}
        </p>
        <p className="text-xs text-muted-light mt-1">
          Bias audit: mean score shift with identity removed {summary.bias_summary.mean_score_delta >= 0 ? "+" : ""}
          {summary.bias_summary.mean_score_delta.toFixed(2)} pts (largest single shift {summary.bias_summary.max_abs_score_delta.toFixed(1)} pts)
        </p>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {BANDS.map((band) => (
          <button
            key={band}
            onClick={() => setFilterMode(filterMode === band ? null : band)}
            className={cn(
              "rounded-lg border p-3.5 text-left transition-colors",
              filterMode === band ? "border-accent bg-accent-light" : "border-border bg-surface hover:border-accent-border hover:bg-accent-light/40"
            )}
          >
            <div className="text-xs text-muted">{band}</div>
            <div className="text-xl font-bold font-tabular text-foreground mt-0.5">{summary.band_counts[band] || 0}</div>
          </button>
        ))}
        <button
          onClick={() => setFilterMode(filterMode === "FLAGGED" ? null : "FLAGGED")}
          className={cn(
            "rounded-lg border p-3.5 text-left transition-colors",
            filterMode === "FLAGGED" ? "border-integrity-flag bg-integrity-flag-bg" : "border-border bg-surface hover:border-integrity-flag/40 hover:bg-integrity-flag-bg/40"
          )}
        >
          <div className="text-xs text-integrity-flag flex items-center gap-1"><Flag size={11} /> Flagged</div>
          <div className="text-xl font-bold font-tabular text-integrity-flag mt-0.5">{summary.flagged_count}</div>
        </button>
      </div>

      {filterMode === "FLAGGED" && (
        <Card className="p-4 bg-integrity-flag-bg border-integrity-flag/20">
          <p className="text-sm text-foreground">
            Candidates whose resumes triggered a Stage 2 integrity check (hidden text, tiny fonts,
            off-page content, OCR mismatch, or keyword stuffing). This is a separate signal from fit
            score — a flagged candidate can still be a strong match. Manual review recommended.
          </p>
        </Card>
      )}

      {/* Filters / search / sort */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-light" />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search candidates..."
            className="w-full h-9 rounded-md border border-border bg-white pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
          />
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <ArrowUpDown size={14} className="text-muted" />
          <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="score_desc">Highest Match</SelectItem>
              <SelectItem value="score_asc">Lowest Match</SelectItem>
              <SelectItem value="experience_desc">Most Experience</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Candidate list */}
      <div className="flex flex-col gap-3">
        {visible.length === 0 && (
          <Card className="p-8 text-center text-sm text-muted">No candidates match the current filters.</Card>
        )}
        {visible.map((c) => {
          const integrity = INTEGRITY_ICON[c.integrity_status] || INTEGRITY_ICON.UNKNOWN;
          return (
            <Card
              key={c.resume_id}
              className="p-4 cursor-pointer hover:border-accent-border transition-colors"
              onClick={() => { setDrawerResumeId(c.resume_id); setDrawerOpen(true); }}
            >
              <div className="flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-foreground truncate">{c.headline || "Untitled"}</div>
                  <div className="text-xs text-muted">{c.resume_id}</div>
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {c.matched_skills.slice(0, 4).map((s) => (
                      <span key={s} className="text-[11px] bg-accent-light text-accent-hover rounded-full px-2 py-0.5">{s}</span>
                    ))}
                    {c.missing_skills.slice(0, 1).map((s) => (
                      <span key={s} className="text-[11px] bg-band-low-bg text-band-low rounded-full px-2 py-0.5">missing: {s}</span>
                    ))}
                  </div>
                </div>

                <div className="text-xs text-muted w-20 hidden md:block">
                  {c.years_experience ? `${c.years_experience.toFixed(0)} yrs` : "—"}
                </div>

                <div className="w-28 hidden sm:flex items-center gap-2">
                  <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                    <div className="h-full bg-accent rounded-full" style={{ width: `${Math.min(c.composite_score, 100)}%` }} />
                  </div>
                  <span className="text-xs font-tabular font-semibold text-foreground w-9">{c.composite_score.toFixed(0)}%</span>
                </div>

                <Badge variant={BAND_BADGE[c.band] || "neutral"} className="shrink-0">{c.band}</Badge>

                <div className="shrink-0" title={integrity.label}>
                  <integrity.icon size={17} className={integrity.className} />
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <CandidateDrawer
        screeningId={screeningId}
        resumeId={drawerResumeId}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
      />
    </div>
  );
}
