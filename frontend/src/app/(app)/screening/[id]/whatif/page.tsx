"use client";
import * as React from "react";
import { useParams } from "next/navigation";
import { ArrowUp, ArrowDown, Minus, FlaskConical } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { useScreening } from "@/lib/screening-context";
import {
  getWhatIfSkills, recomputeWhatIf, type WhatIfResult,
} from "@/lib/api";

const OPTIONS = ["Mandatory", "Preferred", "Not Required"] as const;
const BAND_BADGE: Record<string, "strong" | "high" | "review" | "low" | "neutral"> = {
  "Strong Fit": "strong", "High Potential": "high", "Needs Review": "review", "Low Fit": "low",
  Disqualified: "neutral",
};

export default function WhatIfPage() {
  const params = useParams();
  const screeningId = params.id as string;
  const { setActiveScreeningId } = useScreening();

  const [skills, setSkills] = React.useState<string[]>([]);
  const [toggles, setToggles] = React.useState<Record<string, string>>({});
  const [results, setResults] = React.useState<WhatIfResult[]>([]);
  const [prevResults, setPrevResults] = React.useState<WhatIfResult[]>([]);
  const [summary, setSummary] = React.useState<{ total_candidates: number; qualified_count: number } | null>(null);
  const [prevQualified, setPrevQualified] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setActiveScreeningId(screeningId);
    (async () => {
      const s = await getWhatIfSkills(screeningId);
      setSkills(s);
      const initialToggles = Object.fromEntries(s.map((skill) => [skill, "Preferred"]));
      setToggles(initialToggles);
      const { results, summary } = await recomputeWhatIf(screeningId, initialToggles);
      setResults(results);
      setSummary(summary);
      setPrevQualified(summary.qualified_count);
      setLoading(false);
    })();
  }, [screeningId, setActiveScreeningId]);

  async function handleToggleChange(skill: string, value: string) {
    const newToggles = { ...toggles, [skill]: value };
    setToggles(newToggles);
    setPrevResults(results);
    if (summary) setPrevQualified(summary.qualified_count);
    const { results: newResults, summary: newSummary } = await recomputeWhatIf(screeningId, newToggles);
    setResults(newResults);
    setSummary(newSummary);
  }

  const prevRankMap = React.useMemo(() => {
    const sorted = [...prevResults].sort((a, b) => b.new_composite_score - a.new_composite_score);
    return new Map(sorted.map((r, i) => [r.resume_id, i]));
  }, [prevResults]);

  const sortedResults = React.useMemo(
    () => [...results].sort((a, b) => b.new_composite_score - a.new_composite_score),
    [results]
  );

  const mandatoryCount = Object.values(toggles).filter((v) => v === "Mandatory").length;
  const qualifiedDelta = summary && prevQualified !== null ? summary.qualified_count - prevQualified : 0;

  if (loading) {
    return <div className="text-sm text-muted py-10 text-center">Loading skill preferences…</div>;
  }

  if (skills.length === 0) {
    return (
      <Card className="p-8 text-center text-sm text-muted">
        No individual skill phrases could be extracted from the required-skills text for this screening.
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Skill Preferences & What-If Analysis</h2>
        <p className="text-sm text-muted mt-1">
          Adjust requirement priorities and instantly understand how they affect candidate rankings.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Skill Importance</CardTitle>
          <CardDescription>Set each skill&apos;s importance — the shortlist recomputes live, no re-scoring from scratch.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {skills.map((skill) => (
              <div key={skill} className="flex items-center justify-between px-5 py-3">
                <span className="text-sm font-medium text-foreground">{skill}</span>
                <div className="w-44">
                  <Select value={toggles[skill]} onValueChange={(v) => handleToggleChange(skill, v)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <Card className="p-4">
            <div className="text-xs text-muted">Qualified Candidates</div>
            <div className="flex items-end gap-2 mt-1">
              <span className="text-2xl font-bold font-tabular text-foreground">{summary.qualified_count}</span>
              {qualifiedDelta !== 0 && (
                <span className={`text-xs font-semibold flex items-center gap-0.5 mb-1 ${qualifiedDelta > 0 ? "text-band-strong" : "text-band-low"}`}>
                  {qualifiedDelta > 0 ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
                  {Math.abs(qualifiedDelta)}
                </span>
              )}
            </div>
          </Card>
          <Card className="p-4">
            <div className="text-xs text-muted">Total Shortlist</div>
            <div className="text-2xl font-bold font-tabular text-foreground mt-1">{summary.total_candidates}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs text-muted">Mandatory Skills Set</div>
            <div className="text-2xl font-bold font-tabular text-foreground mt-1">{mandatoryCount}</div>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <FlaskConical size={16} className="text-accent" />
            <CardTitle>Recomputed Ranking</CardTitle>
          </div>
          <CardDescription>Ranking change vs. the previous preference setting</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {sortedResults.map((r, i) => {
            const prevRank = prevRankMap.get(r.resume_id);
            const rankChange = prevRank !== undefined ? prevRank - i : 0;
            return (
              <div
                key={r.resume_id}
                className="flex items-center gap-4 rounded-md border border-border px-4 py-3 bg-white"
              >
                <div className="w-6 text-xs font-tabular font-semibold text-muted text-center">#{i + 1}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-foreground truncate">{r.headline || r.resume_id}</div>
                  <div className="text-xs text-muted">{r.resume_id} · {r.qualified ? "Qualified" : "Disqualified"}</div>
                  {r.missing_mandatory.length > 0 && (
                    <div className="text-[11px] text-band-low mt-0.5">Missing mandatory: {r.missing_mandatory.join(", ")}</div>
                  )}
                </div>
                <div className="text-xs font-tabular text-muted w-24 text-right">
                  {r.new_composite_score.toFixed(1)}
                  <span className={r.new_composite_score >= r.original_composite_score ? "text-band-strong" : "text-band-low"}>
                    {" "}({r.new_composite_score >= r.original_composite_score ? "+" : ""}{(r.new_composite_score - r.original_composite_score).toFixed(1)})
                  </span>
                </div>
                <Badge variant={BAND_BADGE[r.new_band] || "neutral"} className="w-28 justify-center shrink-0">
                  {r.new_band}
                </Badge>
                <div className="w-10 flex justify-center">
                  {rankChange > 0 && <span className="text-band-strong flex items-center text-xs font-semibold"><ArrowUp size={13} />{rankChange}</span>}
                  {rankChange < 0 && <span className="text-band-low flex items-center text-xs font-semibold"><ArrowDown size={13} />{Math.abs(rankChange)}</span>}
                  {rankChange === 0 && <Minus size={13} className="text-muted-light" />}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
