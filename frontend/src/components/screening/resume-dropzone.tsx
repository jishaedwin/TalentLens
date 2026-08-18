"use client";
import * as React from "react";
import { UploadCloud, FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ResumeDropzone({
  files, onChange,
}: { files: File[]; onChange: (files: File[]) => void }) {
  const [dragOver, setDragOver] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  function addFiles(newFiles: FileList | null) {
    if (!newFiles) return;
    const pdfs = Array.from(newFiles).filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    const existingNames = new Set(files.map((f) => f.name));
    const merged = [...files, ...pdfs.filter((f) => !existingNames.has(f.name))];
    onChange(merged);
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center cursor-pointer transition-colors",
          dragOver ? "border-accent bg-accent-light" : "border-border bg-background hover:bg-accent-light/40 hover:border-accent-border"
        )}
      >
        <div className="h-11 w-11 rounded-full bg-accent-light text-accent-hover flex items-center justify-center">
          <UploadCloud size={20} />
        </div>
        <div className="text-sm font-medium text-foreground">
          Drag & drop resume PDFs here, or click to browse
        </div>
        <div className="text-xs text-muted">Supports multiple PDF files</div>
        <input
          ref={inputRef} type="file" accept=".pdf,application/pdf" multiple
          className="hidden" onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs font-medium text-muted">{files.length} resume(s) uploaded</div>
          <div className="max-h-56 overflow-y-auto flex flex-col gap-1.5 pr-1">
            {files.map((f) => (
              <div
                key={f.name}
                className="flex items-center gap-3 rounded-md border border-border bg-white px-3 py-2 text-sm"
              >
                <FileText size={16} className="text-accent shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="truncate font-medium text-foreground">{f.name}</div>
                  <div className="text-[11px] text-muted">{formatBytes(f.size)} · Ready to parse</div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); onChange(files.filter((x) => x.name !== f.name)); }}
                  className="text-muted hover:text-band-low p-1 rounded"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
