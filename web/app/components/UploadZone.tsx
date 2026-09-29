"use client";

import { useRef, useState } from "react";
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
      className={`mx-auto max-w-xl rounded-2xl border-2 border-dashed p-6 text-center transition ${
        over ? "border-accent bg-accent-soft" : "border-border-strong bg-surface hover:border-accent/60"
      }`}
    >
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
        <Upload width={22} height={22} />
      </div>
      <div className="text-[15px] font-semibold">{hasDocs ? "Add more documents" : "Start by adding your documents"}</div>
      <p className="mx-auto mt-1 max-w-sm text-[13px] text-muted">
        Drag files here, or choose them from your computer. Fathom indexes them so you can ask questions and get cited answers.
      </p>
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy}
        className="mt-4 inline-flex items-center gap-2 rounded-lg bg-accent-strong px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:brightness-110 disabled:opacity-60"
      >
        <Upload width={15} height={15} /> {busy ? "Uploading…" : "Choose files"}
      </button>
      <div className="mt-2.5 text-[11px] text-muted">.txt · .md · .pdf · up to 10 MB each · multiple files OK</div>
      <input ref={input} type="file" multiple accept=".txt,.md,.pdf" className="hidden" onChange={(e) => (e.target.files && onFiles(e.target.files), (e.target.value = ""))} />
    </div>
  );
}
