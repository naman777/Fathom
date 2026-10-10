"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Alert, Branch, Check, Chevron, Copy, Eye, Search, Sparkle } from "./icons";
import RequestStats from "./RequestStats";
import type { Msg, Source, Trace } from "./types";

export default function Assistant({ m, onCite, onOpenSources }: { m: Msg; onCite: (s: Source) => void; onOpenSources: () => void }) {
  const [copied, setCopied] = useState(false);
  const sources = m.sources || [];

  // Turn [n] markers into markdown links we can style as citation chips.
  const md = useMemo(
    () => m.content.replace(/\[(\d+)\]/g, (_, n) => (sources.some((s) => s.n === Number(n)) ? `[${n}](#cite-${n})` : `[${n}]`)),
    [m.content, sources]
  );

  return (
    <div className="fade-up flex gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-foreground/[0.06] text-highlight">
        <Sparkle width={15} height={15} />
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {(m.trace?.length ?? 0) > 0 && <TracePanel trace={m.trace!} streaming={!!m.streaming} hasAnswer={!!m.content} />}

        {m.streaming && !m.content && !m.error && <Skeleton />}

        {m.error ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-danger/30 p-3.5 text-sm text-danger">
            <Alert className="mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">{m.error.message}</div>
              {m.error.retryAfter ? <div className="mt-0.5 text-xs opacity-80">You can try again in about {fmtWait(m.error.retryAfter)}.</div> : null}
            </div>
          </div>
        ) : (
          m.content && (
            <div className="prose-fathom">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children }) => {
                    const mm = /^#cite-(\d+)$/.exec(href || "");
                    if (mm) {
                      const src = sources.find((s) => s.n === Number(mm[1]));
                      return (
                        <button className="cite" title={src ? `${src.title} · chunk ${src.position}` : ""} onClick={() => src && onCite(src)}>
                          {mm[1]}
                        </button>
                      );
                    }
                    // Model output is untrusted (a poisoned document may try to steer it): only plain http(s) links, no images.
                    if (!/^https?:\/\//i.test(href || "")) return <span>{children}</span>;
                    return <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-highlight underline underline-offset-2">{children}</a>;
                  },
                  img: ({ alt }) => <span className="text-muted-foreground" title="Images in answers are blocked">[image blocked{alt ? `: ${alt}` : ""}]</span>,
                }}
              >
                {md}
              </ReactMarkdown>
              {m.streaming && <span className="caret" />}
            </div>
          )
        )}

        {sources.length > 0 && !m.streaming && !m.error && <SourcesBar sources={sources} content={m.content} onOpen={onOpenSources} onCite={onCite} />}

        {!m.streaming && !m.error && m.content && (
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            <button
              className="flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-surface-2 hover:text-foreground"
              onClick={() => {
                navigator.clipboard?.writeText(m.content);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
            >
              {copied ? <Check width={13} height={13} /> : <Copy width={13} height={13} />}
              {copied ? "Copied" : "Copy"}
            </button>
            {!m.meta && m.timing?.total !== undefined && (
              <span className="tabular-nums">
                retrieval {sec(m.timing.retrieval)} · first token {sec(m.timing.first)} · total {sec(m.timing.total)}
              </span>
            )}
          </div>
        )}
        {!m.streaming && !m.error && m.meta && <RequestStats meta={m.meta} />}
      </div>
    </div>
  );
}

const sec = (ms?: number) => (ms === undefined ? "–" : `${(ms / 1000).toFixed(1)}s`);
const fmtWait = (s: number) => (s >= 3600 ? `${Math.ceil(s / 3600)} h` : s >= 60 ? `${Math.ceil(s / 60)} min` : `${s}s`);

function Skeleton() {
  return (
    <div className="space-y-2 pt-1">
      <div className="shimmer h-3 w-3/4 rounded" />
      <div className="shimmer h-3 w-1/2 rounded" />
    </div>
  );
}

function TracePanel({ trace, streaming, hasAnswer }: { trace: Trace[]; streaming: boolean; hasAnswer: boolean }) {
  const steps = trace.filter((t) => t.type !== "sources");
  const [open, setOpen] = useState(true);
  useEffect(() => {
    if (hasAnswer || !streaming) setOpen(false);
  }, [hasAnswer, streaming]);

  const last = steps[steps.length - 1];
  const summary = streaming && !hasAnswer ? liveLabel(last) : `Reasoned in ${steps.filter((s) => s.type === "search").length || 1} search${steps.filter((s) => s.type === "search").length > 1 ? "es" : ""}`;

  return (
    <div className="card-chai overflow-hidden">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-xs text-fg-2 hover:bg-surface-2">
        {streaming && !hasAnswer ? <span className="h-1.5 w-1.5 rounded-full bg-primary motion-safe:animate-pulse" /> : <Check width={13} height={13} className="text-success" />}
        <span className="flex-1 text-left font-medium">{summary}</span>
        <span className="text-muted-foreground">{steps.length} steps</span>
        <Chevron width={14} height={14} className={`text-muted-foreground transition ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <ol className="space-y-2.5 border-t border-border px-3.5 py-3">
          {steps.map((t, i) => (
            <Step key={i} t={t} />
          ))}
        </ol>
      )}
    </div>
  );
}

function liveLabel(t?: Trace) {
  if (!t) return "Thinking…";
  if (t.type === "plan") return "Planning searches…";
  if (t.type === "search") return `Searching: ${t.query}`;
  if (t.type === "results") return "Ranking passages…";
  if (t.type === "reflect") return "Checking evidence…";
  return "Working…";
}

function Step({ t }: { t: Trace }) {
  const row = (icon: React.ReactNode, title: string, body?: React.ReactNode) => (
    <li className="flex gap-2.5 text-xs">
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-surface-2 text-muted-foreground">{icon}</span>
      <div className="min-w-0">
        <div className="font-medium text-fg-2">{title}</div>
        {body && <div className="mt-0.5 text-muted-foreground">{body}</div>}
      </div>
    </li>
  );
  if (t.type === "plan")
    return row(<Branch width={12} height={12} />, t.sub_questions.length > 1 ? `Split into ${t.sub_questions.length} sub-questions` : "Single-step question", t.sub_questions.length > 1 ? t.sub_questions.join(" · ") : null);
  if (t.type === "search") return row(<Search width={12} height={12} />, `Search ${t.hop}`, `“${t.query}”`);
  if (t.type === "results") return row(<Eye width={12} height={12} />, `${t.count} passages retrieved`, (t.titles || []).join(", "));
  if (t.type === "reflect")
    return row(<Sparkle width={12} height={12} />, t.sufficient ? "Evidence is sufficient" : "Evidence incomplete, following up", t.sufficient ? null : `Missing: ${t.missing}`);
  return null;
}

function SourcesBar({ sources, content, onOpen, onCite }: { sources: Source[]; content: string; onOpen: () => void; onCite: (s: Source) => void }) {
  const citedN = new Set((content.match(/\[(\d+)\]/g) || []).map((x) => Number(x.slice(1, -1))));
  const docs = new Map<string, Source[]>();
  for (const s of sources) docs.set(s.title, [...(docs.get(s.title) || []), s]);
  return (
    <div className="card-chai">
      <button onClick={onOpen} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-surface-2">
        <span className="flex -space-x-1.5">
          {sources.slice(0, 4).map((s) => (
            <span key={s.n} className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-surface bg-foreground/[0.06] text-[10px] font-semibold text-highlight">
              {s.n}
            </span>
          ))}
          {sources.length > 4 && (
            <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-surface bg-surface-3 text-[10px] text-muted-foreground">+{sources.length - 4}</span>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-montserrat text-xs font-semibold text-foreground">
            {sources.length} passage{sources.length === 1 ? "" : "s"} from {docs.size} document{docs.size === 1 ? "" : "s"}
          </span>
          <span className="block truncate text-[11px] text-muted-foreground">{Array.from(docs.keys()).join(" · ")}</span>
        </span>
        <span className="flex items-center gap-1 text-[11px] font-medium text-highlight">
          View <Chevron width={13} height={13} />
        </span>
      </button>
      <div className="flex flex-wrap gap-1.5 border-t border-border px-3 py-2">
        {sources.map((s) => (
          <button
            key={s.n}
            onClick={() => onCite(s)}
            title={s.content.slice(0, 160)}
            className={`flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] transition hover:border-card-edge-hover hover:text-foreground ${
              citedN.has(s.n) ? "border-card-edge-hover bg-foreground/[0.06] text-highlight" : "border-border text-muted-foreground"
            }`}
          >
            <span className="font-semibold">{s.n}</span>
            <span className="truncate">passage {s.position + 1}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
