import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "bg-accent-light text-accent-hover border border-accent-border",
        strong: "bg-band-strong-bg text-band-strong",
        high: "bg-band-high-bg text-band-high",
        review: "bg-band-review-bg text-band-review",
        low: "bg-band-low-bg text-band-low",
        flagged: "bg-integrity-flag-bg text-integrity-flag",
        ok: "bg-integrity-ok-bg text-integrity-ok",
        neutral: "bg-background text-muted border border-border",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
