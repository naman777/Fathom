"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Close, Copy, Download, File } from "./icons";
import type { Source } from "./types";

export type PanelState = { sources: Source[]; cited: number[]; focus?: number };

export default function SourcesPanel({
  panel,
  onClose,
  canDownload,
  onDownload,
}: {
  panel: PanelState;
  onClose: () => void;
  canDownload: (title: string) => boolean;
  onDownload: (title: string) => void;
}) {
  const { sources, cited, focus } = panel;
  const [citedOnly, setCitedOnly] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const refs = useRef<Record<number, HTMLElement | null>>({});

  const visible = citedOnly ? sources.filter((s) => cited.includes(s.n)) : sources;
  const groups = useMemo(() => {
    const map = new Map<string, Source[]>();
    for (const s of visible) map.set(s.title, [...(map.get(s.title) || []), s]);
    return Array.from(map.entries());
  }, [visible]);
  const docCount = new Set(sources.map((s) => s.title)).size;

  // Jump to the clicked citation and expand it.
  useEffect(() => {
    if (focus === undefined) return;
    setCitedOnly(false);
    setExpanded((e) => ({ ...e, [focus]: true }));
    const t = setTimeout(() => refs.current[focus]?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
    return () => clearTimeout(t);
  }, [focus, sources]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm lg:hidden" onClick={onClose} />
      <aside className="fade-up fixed inset-y-0 right-0 z-50 flex w-full max-w-[480px] flex-col border-l border-border bg-surface lg:static lg:z-auto lg:w-[440px] lg:max-w-none lg:shrink-0">
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <div className="font-montserrat text-sm font-semibold">Sources</div>
            <div className="text-xs text-muted-foreground">
              {sources.length} passage{sources.length === 1 ? "" : "s"} · {docCount} document{docCount === 1 ? "" : "s"}
              {cited.length > 0 && <> · {cited.length} cited</>}
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-2 hover:text-foreground" aria-label="Close sources">
            <Close />
          </button>
        </div>

        {cited.length > 0 && cited.length < sources.length && (
          <div className="flex gap-1 border-b border-border px-4 py-2 text-xs">
            {[
              { v: false, label: `All (${sources.length})` },
              { v: true, label: `Cited in answer (${cited.length})` },
            ].map((o) => (
              <button
                key={String(o.v)}
                onClick={() => setCitedOnly(o.v)}
                className={`rounded-full px-3 py-1 transition ${citedOnly === o.v ? "bg-foreground/[0.06] font-medium text-highlight" : "text-muted-foreground hover:bg-surface-2 hover:text-foreground"}`}
              >
                {o.label}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          {groups.map(([title, items]) => (
            <section key={title}>
              <div className="mb-2 flex items-center gap-2">
                <File width={14} height={14} className="shrink-0 text-muted-foreground" />
                <h3 className="min-w-0 flex-1 truncate text-xs font-semibold text-foreground" title={title}>
                  {title}
                </h3>
                {canDownload(title) && (
                  <button onClick={() => onDownload(title)} className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-surface-2 hover:text-foreground" title="Download original file">
                    <Download width={12} height={12} /> Original
                  </button>
                )}
              </div>
              <div className="space-y-2">
                {items.map((s) => {
                  const isCited = cited.includes(s.n);
                  const isFocus = focus === s.n;
                  const open = expanded[s.n];
                  const long = s.content.length > 380;
                  return (
                    <article
                      key={s.n}
                      ref={(el) => {
                        refs.current[s.n] = el;
                      }}
                      className={`rounded-xl border p-3 transition ${isFocus ? "border-card-edge-hover bg-foreground/[0.06] ring-1 ring-card-edge-hover" : "border-border bg-background/40"}`}
                    >
                      <div className="mb-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                        <span className="flex h-5 min-w-5 items-center justify-center rounded-md bg-foreground/[0.06] px-1 font-semibold text-highlight">{s.n}</span>
                        <span>Passage {s.position + 1}</span>
                        {isCited && (
                          <span className="flex items-center gap-1 rounded-full border border-success/30 px-1.5 py-0.5 text-success">
                            <Check width={10} height={10} /> cited
                          </span>
                        )}
                        <button
                          className="ml-auto rounded p-1 hover:bg-surface-2 hover:text-foreground"
                          aria-label="Copy passage"
                          onClick={() => {
                            navigator.clipboard?.writeText(s.content);
                            setCopied(s.n);
                            setTimeout(() => setCopied(null), 1500);
                          }}
                        >
                          {copied === s.n ? <Check width={12} height={12} className="text-success" /> : <Copy width={12} height={12} />}
                        </button>
                      </div>
                      <div className={`prose-fathom source-md text-[13px] ${long && !open ? "line-clamp-6" : ""}`}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.content}</ReactMarkdown>
                      </div>
                      {long && (
                        <button onClick={() => setExpanded((e) => ({ ...e, [s.n]: !open }))} className="mt-1.5 text-[11px] font-medium text-highlight hover:underline">
                          {open ? "Show less" : "Show more"}
                        </button>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
          {groups.length === 0 && <p className="py-8 text-center text-xs text-muted-foreground">No passages to show.</p>}
        </div>
      </aside>
    </>
  );
}
