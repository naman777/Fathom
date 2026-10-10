"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Upload } from "./icons";

/** Large, obvious drop target + file picker. Used in the empty chat state, where it is the first thing a new user sees. */
export default function UploadZone({ onFiles, busy, hasDocs }: { onFiles: (f: FileList | File[]) => void; busy: boolean; hasDocs: boolean }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFiles(e.dataTransfer.files);
      }}
      className={`card-chai mx-auto max-w-xl border-dashed p-6 text-center ${over ? "border-card-edge-hover bg-foreground/[0.06]" : ""}`}
    >
      <div className="font-montserrat text-base font-semibold">{hasDocs ? "Add more documents" : "Start by adding your documents"}</div>
      <p className="mx-auto mt-1 max-w-sm text-[13px] text-muted-foreground">
        Drag files here, or choose them from your computer. Fathom indexes them so you can ask questions and get cited answers.
      </p>
      <Button type="button" onClick={() => input.current?.click()} disabled={busy} className="mt-4">
        <Upload width={15} height={15} /> {busy ? "Uploading…" : "Choose files"}
      </Button>
      <div className="mt-2.5 text-[11px] text-muted-foreground">.txt · .md · .pdf · up to 10 MB each · multiple files OK</div>
      <input ref={input} type="file" multiple accept=".txt,.md,.pdf" className="hidden" onChange={(e) => (e.target.files && onFiles(e.target.files), (e.target.value = ""))} />
    </div>
  );
}
