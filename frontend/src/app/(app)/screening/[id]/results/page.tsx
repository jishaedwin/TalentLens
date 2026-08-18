"use client";
import * as React from "react";
import { useParams } from "next/navigation";
import { FileDown, FileSpreadsheet, Users, Trophy, Eye, ShieldAlert } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { useScreening } from "@/lib/screening-context";
import {
  getScreeningSummary, getCandidates, pdfReportUrl, excelReportUrl,
  type ScreeningSummary, type Candidate,
} from "@/lib/api";

const BAND_BADGE: Record<string, "strong" | "high" | "review" | "low"> = {
  "Strong Fit": "strong", "High Potential": "high", "Needs Review": "review", "Low Fit": "low",
};

export default function ResultsPage() {
  const params = useParams();
  const screeningId = params.id as string;
  const { setActiveScreeningId } = useScreening();

  const [summary, setSummary] = React.useState<ScreeningSummary | null>(null);
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setActiveScreeningId(screeningId);
    (async () => {
      const [s, c] = await Promise.all([getScreeningSummary(screeningId), getCandidates(screeningId)]);
      setSummary(s);
      setCandidates(c.candidates);
      setLoading(false);
    })();
  }, [screeningId, setActiveScreeningId]);

  if (loading || !summary) {
    return <div className="text-sm text-muted py-10 text-center">Loading results…</div>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Screening Results</h2>
        <p className="text-sm text-muted mt-1">
          Review the final candidate ranking and export the results for your recruitment workflow.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Total Screened" value={summary.total_candidates} icon={Users} iconClassName="bg-accent-light text-accent-hover" />
        <KpiCard label="Strong Matches" value={summary.band_counts["Strong Fit"] || 0} icon={Trophy} iconClassName="bg-band-strong-bg text-band-strong" />
        <KpiCard label="Needs Review" value={summary.band_counts["Needs Review"] || 0} icon={Eye} iconClassName="bg-band-review-bg text-band-review" />
        <KpiCard label="Flagged" value={summary.flagged_count} icon={ShieldAlert} iconClassName="bg-integrity-flag-bg text-integrity-flag" />
      </div>

      <Card className="border-accent-border bg-accent-light/40">
        <CardHeader>
          <CardTitle>Export Results</CardTitle>
          <CardDescription>Download a shareable report for hiring managers, HR, or interview panels.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <a href={pdfReportUrl(screeningId)} download>
            <Button size="lg" className="gap-2"><FileDown size={16} /> Download PDF Report</Button>
          </a>
          <a href={excelReportUrl(screeningId)} download>
            <Button size="lg" variant="secondary" className="gap-2"><FileSpreadsheet size={16} /> Download Excel</Button>
          </a>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Final Candidate Ranking</CardTitle>
          <CardDescription>{summary.job_description.job_title}</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-t border-border text-left text-xs text-muted">
                <th className="font-medium px-5 py-2.5">#</th>
                <th className="font-medium px-3 py-2.5">Candidate</th>
                <th className="font-medium px-3 py-2.5">Score</th>
                <th className="font-medium px-3 py-2.5">Band</th>
                <th className="font-medium px-3 py-2.5">Experience</th>
                <th className="font-medium px-5 py-2.5">Integrity</th>
              </tr>
            </thead>
            <tbody>
              {[...candidates]
                .sort((a, b) => b.composite_score - a.composite_score)
                .map((c, i) => (
                  <tr key={c.resume_id} className="border-t border-border">
                    <td className="px-5 py-2.5 text-muted font-tabular">{i + 1}</td>
                    <td className="px-3 py-2.5">
                      <div className="font-medium text-foreground">{c.headline || "Untitled"}</div>
                      <div className="text-xs text-muted">{c.resume_id}</div>
                    </td>
                    <td className="px-3 py-2.5 font-tabular font-semibold">{c.composite_score.toFixed(1)}</td>
                    <td className="px-3 py-2.5"><Badge variant={BAND_BADGE[c.band] || "neutral"}>{c.band}</Badge></td>
                    <td className="px-3 py-2.5 text-muted">{c.years_experience ? `${c.years_experience.toFixed(0)}y` : "—"}</td>
                    <td className="px-5 py-2.5 text-xs text-muted">{c.integrity_status.replace("_", " ")}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
