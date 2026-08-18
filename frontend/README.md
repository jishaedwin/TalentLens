# TalentLens Frontend (Next.js)

A complete rebuild of the TalentLens UI — Next.js (App Router) + Tailwind CSS v4
+ hand-written shadcn-style components (Radix primitives + CVA, the same
approach the shadcn CLI itself uses under the hood) + lucide-react icons +
Recharts. Talks to the FastAPI backend (`../talentlens-backend`) over REST —
no ML/matching logic lives in this project.

## Setup

```bash
npm install
```

Create `.env.local`:
```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Run

```bash
npm run dev
```
Opens at http://localhost:3000. The backend must be running at the URL above
(CORS is pre-configured on the backend for `localhost:3000`).

## Structure

```
src/
  app/
    (app)/                    — app shell (sidebar + topbar) wraps every page
      dashboard/               — KPIs, charts, recent screening sessions
      screening/new/           — data source toggle, JD form, upload, progress
      screening/[id]/shortlist/  — KPI tiles incl. dedicated integrity "Flagged" tile,
                                    search/sort, candidate list + detail drawer
      screening/[id]/whatif/     — skill importance dropdowns, live recompute,
                                    before/after ranking comparison
      screening/[id]/results/    — final ranking + PDF/Excel export
  components/
    ui/                        — Button, Card, Badge, Input, Textarea, Select,
                                   Progress, Sheet (drawer) — hand-written primitives
    shell/                     — Sidebar, Topbar
    screening/                 — SkillChipInput, ResumeDropzone, ProcessingProgress,
                                   CandidateDrawer
    dashboard/                 — KpiCard
  lib/
    api.ts                     — typed REST client for every backend endpoint
    screening-context.tsx      — tracks the "active screening" across pages/sidebar
    utils.ts                   — cn() className helper
```

## Design system

Defined as CSS custom properties in `src/app/globals.css` (Tailwind v4's
CSS-based theme config — no `tailwind.config.js`):
- **Accent:** TalentLens orange (`#EA580C`), used only for primary actions,
  active nav states, and key highlights — not decoratively elsewhere.
- **Match-band palette:** green/blue/amber/red, reused identically everywhere
  a band appears (tiles, badges, charts, PDF report).
- **Integrity/fraud color:** violet, deliberately distinct from both the accent
  and the "Low Fit" red, so a flag never reads as "just a bad score."
- System font stack (not Google Fonts — see note below) with a monospace
  stack reserved for tabular numeric scores.

## A build issue worth knowing about

`next/font/google` (the default in `create-next-app`) failed to build in this
sandbox — Google Fonts' CDN isn't reachable from this network (the same class
of restriction that blocked HuggingFace Hub for the ML side of this project).
Switched to system font stacks before it could become a shipped bug. If your
environment can reach Google Fonts, swapping in a real webfont is a one-line
change in `globals.css` + `layout.tsx`.

## Known scope gaps (honest, not hidden)

- **Per-candidate PDF report** is not wired up — the button in the candidate
  drawer is visibly disabled with an explanatory tooltip rather than silently
  doing nothing. Only the full-screening report is implemented.
- **Filters** on the Shortlist page cover match category (via tiles), search,
  and sort (score/experience) — score-range slider, location, and a dedicated
  education filter from the original spec weren't built (location isn't even
  extracted by the pipeline; the others were deprioritized given the scope).
- Charts on the Dashboard reflect the **most recent** screening only, not an
  aggregate across all history — there wasn't a backend aggregate endpoint for
  cross-screening skill/band trends, and fabricating one felt riskier than
  being upfront about the scope.
