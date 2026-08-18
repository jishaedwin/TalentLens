"use client";
import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export function SkillChipInput({
  value, onChange, placeholder,
}: { value: string[]; onChange: (skills: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = React.useState("");

  function commit() {
    const trimmed = draft.trim().replace(/,$/, "");
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed]);
    }
    setDraft("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5 min-h-9 w-full rounded-md border border-border bg-white px-2.5 py-1.5",
        "focus-within:ring-2 focus-within:ring-accent/30 focus-within:border-accent transition-colors"
      )}
      onClick={(e) => {
        if (e.currentTarget === e.target) (e.currentTarget.querySelector("input") as HTMLInputElement)?.focus();
      }}
    >
      {value.map((skill) => (
        <span
          key={skill}
          className="inline-flex items-center gap-1 rounded-full bg-accent-light text-accent-hover border border-accent-border text-xs font-medium pl-2.5 pr-1.5 py-0.5"
        >
          {skill}
          <button
            type="button"
            onClick={() => onChange(value.filter((s) => s !== skill))}
            className="hover:bg-accent-border/60 rounded-full p-0.5"
          >
            <X size={11} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commit}
        placeholder={value.length === 0 ? placeholder : ""}
        className="flex-1 min-w-[120px] text-sm outline-none py-0.5 placeholder:text-muted-light"
      />
    </div>
  );
}
