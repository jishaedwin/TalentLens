"use client";
import * as React from "react";
import Link from "next/link";
import { Users, ListChecks, Trophy, Eye, ShieldAlert, ArrowRight } from "lucide-react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RTooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KpiCard } from "@/components/dashboard/kpi-card";
import {
  getDashboardSummary, getRecentScreenings, getCandidates,
  type RecentScreening,
} from "@/lib/api";

const BAND_CHART_COLORS: Record<string, string> = {
  "Strong Fit": "#15803D",
  "High Potential": "#2563EB",
  "Needs Review": "#B45309",
  "Low Fit": "#DC2626",
};

const BAND_BADGE: Record<string, "strong" | "high" | "review" | "low"> = {
  "Strong Fit": "strong", "High Potential": "high", "Needs Review": "review", "Low Fit": "low",
};

export default function DashboardPage() {
  const [summary, setSummary] = React.useState<Awaited<ReturnType<typeof getDashboardSummary>> | null>(null);
  const [recent, setRecent] = React.useState<RecentScreening[]>([]);
  const [bandDist, setBandDist] = React.useState<{ name: string; value: number }[]>([]);
  const [topSkills, setTopSkills] = React.useState<{ skill: string; count: number }[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    (async () => {
      try {
        const [s, r] = await Promise.all([getDashboardSummary(), getRecentScreenings(10)]);
        setSummary(s);
        setRecent(r);

        if (r.length > 0) {
          const latestId = r[0].screening_id;
          try {
            const { candidates } = await getCandidates(latestId);
            const bandCounts: Record<string, number> = {};
            const skillCounts: Record<string, number> = {};
            for (const c of candidates) {
              bandCounts[c.band] = (bandCounts[c.band] || 0) + 1;
              for (const skill of c.matched_skills) {
                skillCounts[skill] = (skillCounts[skill] || 0) + 1;
              }
            }
            setBandDist(Object.entries(bandCounts).map(([name, value]) => ({ name, value })));
            setTopSkills(
              Object.entries(skillCounts)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8)
                .map(([skill, count]) => ({ skill, count }))
            );
          } catch {
            // The most recent screening's in-memory session may no longer exist
            // (e.g. after a backend restart) even though its summary metadata is
            // still recorded — degrade gracefully rather than breaking the page.
            setBandDist([]);
            setTopSkills([]);
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Good morning, Recruiter</h2>
          <p className="text-sm text-muted mt-1">
            Here&apos;s an overview of your recruitment screening activity.
          </p>
        </div>
        <Link href="/screening/new">
          <Button size="lg" className="gap-2">
            + New Screening
          </Button>
        </Link>
      </div>

      {!loading && summary && summary.total_screenings === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted">
            No screenings yet. Run your first screening — sample data or your own upload — to see activity here.
          </p>
          <Link href="/screening/new" className="inline-block mt-4">
            <Button>Create a screening</Button>
          </Link>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <KpiCard
          label="Candidates Screened" value={summary?.total_screened ?? "—"}
          icon={Users} iconClassName="bg-accent-light text-accent-hover"
          caption={summary ? `across ${summary.total_screenings} screening(s)` : undefined}
        />
        <KpiCard
          label="Shortlisted" value={summary?.total_shortlisted ?? "—"}
          icon={ListChecks} iconClassName="bg-band-high-bg text-band-high"
        />
        <KpiCard
          label="Strong Matches" value={summary?.total_strong ?? "—"}
          icon={Trophy} iconClassName="bg-band-strong-bg text-band-strong"
        />
        <KpiCard
          label="Needs Review" value={bandDist.find((b) => b.name === "Needs Review")?.value ?? "—"}
          icon={Eye} iconClassName="bg-band-review-bg text-band-review"
          caption="most recent screening"
        />
        <KpiCard
          label="Potentially Flagged" value={summary?.total_flagged ?? "—"}
          icon={ShieldAlert} iconClassName="bg-integrity-flag-bg text-integrity-flag"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Candidate Match Distribution</CardTitle>
            <CardDescription>Most recent screening, by fit band</CardDescription>
          </CardHeader>
          <CardContent>
            {bandDist.length === 0 ? (
              <div className="h-56 flex items-center justify-center text-sm text-muted">No data yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={bandDist} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
                    {bandDist.map((entry) => (
                      <Cell key={entry.name} fill={BAND_CHART_COLORS[entry.name] || "#9CA3AF"} />
                    ))}
                  </Pie>
                  <RTooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
            <div className="flex flex-wrap gap-2 mt-2 justify-center">
              {bandDist.map((b) => (
                <Badge key={b.name} variant={BAND_BADGE[b.name] || "neutral"}>
                  {b.name} ({b.value})
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Skills in Shortlisted Candidates</CardTitle>
            <CardDescription>Most common matched skills, most recent screening</CardDescription>
          </CardHeader>
          <CardContent>
            {topSkills.length === 0 ? (
              <div className="h-56 flex items-center justify-center text-sm text-muted">No data yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={topSkills} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E5E7EB" />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: "#6B7280" }} />
                  <YAxis type="category" dataKey="skill" width={90} tick={{ fontSize: 11, fill: "#171923" }} />
                  <RTooltip />
                  <Bar dataKey="count" fill="#EA580C" radius={[0, 4, 4, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Screening Sessions</CardTitle>
          <CardDescription>Your latest AI-powered candidate screenings</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {recent.length === 0 ? (
            <div className="px-5 pb-5 text-sm text-muted">No screening sessions yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-t border-border text-left text-xs text-muted">
                  <th className="font-medium px-5 py-2.5">Job Title</th>
                  <th className="font-medium px-3 py-2.5">Candidates</th>
                  <th className="font-medium px-3 py-2.5">Strong</th>
                  <th className="font-medium px-3 py-2.5">Flagged</th>
                  <th className="font-medium px-3 py-2.5">Date</th>
                  <th className="font-medium px-3 py-2.5">Status</th>
                  <th className="font-medium px-5 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((s) => (
                  <tr key={s.screening_id} className="border-t border-border hover:bg-background/60">
                    <td className="px-5 py-3 font-medium text-foreground">
                      {s.job_title}
                      {s.data_mode === "demo" && (
                        <Badge variant="flagged" className="ml-2 align-middle">Sample</Badge>
                      )}
                    </td>
                    <td className="px-3 py-3 font-tabular">{s.n_candidates}</td>
                    <td className="px-3 py-3 font-tabular text-band-strong">{s.n_strong}</td>
                    <td className="px-3 py-3 font-tabular text-integrity-flag">{s.n_flagged}</td>
                    <td className="px-3 py-3 text-muted">{new Date(s.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-3">
                      <Badge variant="ok">{s.status}</Badge>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Link href={`/screening/${s.screening_id}/shortlist`}>
                        <Button variant="ghost" size="sm" className="gap-1">
                          View <ArrowRight size={13} />
                        </Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
