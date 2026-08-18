"use client";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Search, Bell, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

const PAGE_TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/screening/new": "New Screening",
};

function pageTitleFor(pathname: string): string {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  if (pathname.endsWith("/shortlist")) return "Candidate Shortlist";
  if (pathname.endsWith("/whatif")) return "Skill Preferences & What-If";
  if (pathname.endsWith("/results")) return "Screening Results";
  return "TalentLens";
}

export function Topbar() {
  const pathname = usePathname() || "";
  const title = pageTitleFor(pathname);

  return (
    <header className="h-16 border-b border-border bg-surface/80 backdrop-blur sticky top-0 z-30 flex items-center px-6 gap-4">
      <h1 className="text-base font-semibold text-foreground shrink-0">{title}</h1>

      <div className="flex-1 max-w-md ml-4 relative hidden md:block">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-light" />
        <input
          type="text"
          placeholder="Search candidates..."
          className="w-full h-9 rounded-md border border-border bg-background pl-9 pr-3 text-sm placeholder:text-muted-light focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent focus:bg-white transition-colors"
        />
      </div>

      <div className="ml-auto flex items-center gap-2">
        <Link href="/screening/new">
          <Button size="sm" className="gap-1.5">
            <Plus size={15} /> New Screening
          </Button>
        </Link>
        <button className="h-9 w-9 rounded-md flex items-center justify-center text-muted hover:bg-background hover:text-foreground relative">
          <Bell size={17} />
        </button>
        <div className="h-8 w-8 rounded-full bg-accent-light text-accent-hover flex items-center justify-center text-xs font-semibold border border-accent-border">
          RC
        </div>
      </div>
    </header>
  );
}
