"use client";
import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

const STEPS = [
  { key: "parsing", label: "Parsing resumes & extracting candidate information" },
  { key: "integrity", label: "Running integrity checks" },
  { key: "indexing", label: "Building candidate index" },
  { key: "matching", label: "Matching skills, evaluating experience & compatibility" },
  { key: "bias_audit", label: "Auditing for bias" },
  { key: "explaining", label: "Generating match explanations & ranking candidates" },
];

export function ProcessingProgress({ currentStep, progress }: { currentStep: string | null; progress: number }) {
  const currentIndex = STEPS.findIndex((s) => s.key === currentStep);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex justify-between text-xs text-muted mb-1.5">
          <span>Running AI screening…</span>
          <span className="font-tabular">{Math.round(progress * 100)}%</span>
        </div>
        <Progress value={progress * 100} />
      </div>
      <div className="flex flex-col gap-2.5">
        {STEPS.map((step, i) => {
          const isDone = currentIndex > i || (currentIndex === -1 && progress >= 1);
          const isCurrent = i === currentIndex;
          return (
            <div key={step.key} className="flex items-center gap-3">
              <div
                className={cn(
                  "h-6 w-6 rounded-full flex items-center justify-center shrink-0 border",
                  isDone ? "bg-band-strong border-band-strong text-white" :
                  isCurrent ? "border-accent text-accent" : "border-border text-muted-light"
                )}
              >
                {isDone ? <Check size={13} /> : isCurrent ? <Loader2 size={13} className="animate-spin" /> : <span className="text-[10px]">{i + 1}</span>}
              </div>
              <span className={cn("text-sm", isDone ? "text-foreground" : isCurrent ? "text-foreground font-medium" : "text-muted-light")}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
