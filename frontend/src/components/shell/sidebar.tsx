"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FilePlus2, ListChecks, Users, SlidersHorizontal,
  FlaskConical, FileBarChart, Settings, HelpCircle, ChevronsLeft, ChevronsRight,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useScreening } from "@/lib/screening-context";

function NavLink({
  href, icon: Icon, label, collapsed, disabled, active,
}: {
  href: string; icon: React.ElementType; label: string; collapsed: boolean; disabled?: boolean; active?: boolean;
}) {
  const content = (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        active ? "bg-accent-light text-accent-hover" : "text-foreground/80 hover:bg-background hover:text-foreground",
        disabled && "opacity-40 pointer-events-none",
        collapsed && "justify-center px-0"
      )}
      title={collapsed ? label : undefined}
    >
      <Icon className="h-4.5 w-4.5 shrink-0" size={18} />
      {!collapsed && <span>{label}</span>}
    </div>
  );
  if (disabled) return content;
  return <Link href={href}>{content}</Link>;
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const { activeScreeningId } = useScreening();

  const hasScreening = !!activeScreeningId;
  const shortlistHref = hasScreening ? `/screening/${activeScreeningId}/shortlist` : "#";
  const whatifHref = hasScreening ? `/screening/${activeScreeningId}/whatif` : "#";
  const resultsHref = hasScreening ? `/screening/${activeScreeningId}/results` : "#";

  return (
    <aside
      className={cn(
        "h-screen sticky top-0 flex flex-col border-r border-border bg-surface transition-all duration-200",
        collapsed ? "w-16" : "w-64"
      )}
    >
      <div className={cn("flex items-center gap-2.5 px-4 h-16 border-b border-border", collapsed && "justify-center px-0")}>
        <div className="h-8 w-8 rounded-md bg-accent text-white flex items-center justify-center font-bold text-sm shrink-0">
          TL
        </div>
        {!collapsed && (
          <div className="leading-tight">
            <div className="font-semibold text-sm text-foreground">TalentLens</div>
            <div className="text-[11px] text-muted">AI Recruitment Intelligence</div>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-2.5 py-4 flex flex-col gap-1">
        <NavLink href="/dashboard" icon={LayoutDashboard} label="Dashboard" collapsed={collapsed}
          active={pathname === "/dashboard"} />
        <NavLink href="/screening/new" icon={FilePlus2} label="New Screening" collapsed={collapsed}
          active={pathname === "/screening/new"} />
        <NavLink href={shortlistHref} icon={ListChecks} label="Shortlist" collapsed={collapsed}
          disabled={!hasScreening} active={pathname?.endsWith("/shortlist")} />
        <NavLink href={whatifHref} icon={SlidersHorizontal} label="Skill Preferences" collapsed={collapsed}
          disabled={!hasScreening} active={pathname?.endsWith("/whatif")} />
        <NavLink href={resultsHref} icon={FileBarChart} label="Reports" collapsed={collapsed}
          disabled={!hasScreening} active={pathname?.endsWith("/results")} />
      </nav>

      <div className="px-2.5 py-3 border-t border-border flex flex-col gap-1">
        <NavLink href="#" icon={Settings} label="Settings" collapsed={collapsed} disabled />
        <NavLink href="#" icon={HelpCircle} label="Help" collapsed={collapsed} disabled />
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="mt-1 flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted hover:bg-background hover:text-foreground"
        >
          {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
