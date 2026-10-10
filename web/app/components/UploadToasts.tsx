"use client";

import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { Check, Close } from "./icons";
import type { Job } from "./types";

/** Floating upload progress, visible from anywhere in the app (the sidebar list is hidden on mobile and other tabs). */
export default function UploadToasts({ jobs, onDismiss }: { jobs: Job[]; onDismiss: (id: string) => void }) {
  if (!jobs.length) return null;
  return (
    <div className="pointer-events-none fixed bottom-24 right-4 z-40 flex w-[min(340px,calc(100vw-2rem))] flex-col gap-2" role="status" aria-live="polite">
      {jobs.map((j) => (
        <div key={j.id} className="fade-up pointer-events-auto rounded-xl border border-card-edge-hover bg-card p-3 text-xs">
          <div className="flex items-center gap-2">
            {j.stage === "done" ? (
              <Check width={14} height={14} className="shrink-0 text-success" />
            ) : j.stage === "error" ? (
              <Close width={14} height={14} className="shrink-0 text-danger" />
            ) : (
              <Spinner label="Working" className="shrink-0" />
            )}
            <span className="flex-1 truncate font-medium text-fg-2" title={j.name}>{j.name}</span>
            {j.stage === "uploading" && <span className="tabular-nums text-muted-foreground">{j.pct}%</span>}
            {(j.stage === "error" || j.stage === "done") && (
              <button onClick={() => onDismiss(j.id)} className="text-muted-foreground hover:text-foreground" aria-label="Dismiss">
                <Close width={12} height={12} />
              </button>
            )}
          </div>
          {j.stage === "uploading" && <Progress value={j.pct} aria-label={`Uploading ${j.name}`} className="mt-2 h-1" />}
          {j.stage === "indexing" && <div className="shimmer mt-2 h-1 rounded-full" />}
          <div className={`mt-1.5 ${j.stage === "error" ? "text-danger" : j.stage === "done" ? "text-success" : "text-muted-foreground"}`}>
            {j.stage === "queued" && "Waiting…"}
            {j.stage === "uploading" && "Uploading…"}
            {j.stage === "indexing" && "Reading, chunking and embedding. A few seconds…"}
            {(j.stage === "done" || j.stage === "error") && j.msg}
          </div>
        </div>
      ))}
    </div>
  );
}
