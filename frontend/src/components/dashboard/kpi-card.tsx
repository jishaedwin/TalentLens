import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function KpiCard({
  label, value, icon: Icon, iconClassName, caption,
}: {
  label: string; value: string | number; icon: LucideIcon; iconClassName?: string; caption?: string;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs font-medium text-muted">{label}</div>
          <div className="mt-1.5 text-2xl font-bold text-foreground font-tabular">{value}</div>
          {caption && <div className="mt-1 text-[11px] text-muted-light">{caption}</div>}
        </div>
        <div className={cn("h-9 w-9 rounded-lg flex items-center justify-center shrink-0", iconClassName)}>
          <Icon size={17} />
        </div>
      </div>
    </Card>
  );
}
