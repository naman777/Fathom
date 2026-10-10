"use client";

import { useState } from "react";
import { Chevron } from "./icons";
import type { Meta } from "./types";

export const fmtUsd = (usd: number) => (usd === 0 ? "$0" : usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`);
export const fmtTok = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const sec = (ms?: number | null) => (ms == null ? "–" : `${(ms / 1000).toFixed(1)}s`);

const STAGE_LABEL: Record<string, string> = {
  plan: "Plan", embed: "Embed query", hyde: "HyDE passage", lexical: "Full-text search", dense: "Vector search", rerank: "Rerank",
  reflect: "Reflect", answer: "Answer", retrieval_total: "Retrieval",
};

/** "Cost $0.0043 · 3.4k tokens · 62% rerank" with an expandable stage breakdown for one request. */
export default function RequestStats({ meta }: { meta: Meta }) {
  const [open, setOpen] = useState(false);
  const unpriced = meta.unpriced_models.length > 0;
  const cost = unpriced ? (meta.cost_usd > 0 ? `${fmtUsd(meta.cost_usd)}+` : "price not set") : fmtUsd(meta.cost_usd);
  const top = meta.top_stage ? `${Math.round(meta.stage_share_pct[meta.top_stage])}% ${STAGE_LABEL[meta.top_stage] ?? meta.top_stage}` : null;
  const shares = Object.entries(meta.stage_share_pct);
  return (
    <div className="w-full">
      <button onClick={() => setOpen(!open)} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md px-1.5 py-1 text-left text-[11px] tabular-nums text-muted-foreground hover:bg-surface-2 hover:text-foreground" aria-expanded={open}>
        <span title={unpriced ? `No price configured for: ${meta.unpriced_models.join(", ")}. Set MODEL_PRICES in .env to include them.` : "Estimated from token usage and configured prices"}>
          {cost}
        </span>
        <span>·</span>
        <span title={`${meta.tokens.prompt.toLocaleString()} prompt + ${meta.tokens.completion.toLocaleString()} completion, ${meta.tokens.calls} model calls`}>{fmtTok(meta.tokens.prompt + meta.tokens.completion)} tokens</span>
        {top && (
          <>
            <span>·</span>
            <span title="Share of busy time spent in the slowest stage">{top}</span>
          </>
        )}
        <span>·</span>
        <span>{sec(meta.wall_ms)}</span>
        <Chevron width={12} height={12} className={`transition ${open ? "-rotate-90" : "rotate-90"}`} />
      </button>
      {open && (
        <div className="fade-up card-chai mt-1.5 space-y-3 p-3 text-xs">
          <div>
            <div className="mb-1.5 font-medium text-fg-2">Where the time went</div>
            <ul className="space-y-1">
              {shares.map(([k, pct]) => (
                <li key={k} className="flex items-center gap-2">
                  <span className="w-24 shrink-0 text-muted-foreground">{STAGE_LABEL[k] ?? k}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
                    <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.max(pct, 2)}%` }} />
                  </span>
                  <span className="w-16 shrink-0 text-right tabular-nums text-muted-foreground">{sec(meta.stages_ms[k])} · {Math.round(pct)}%</span>
                </li>
              ))}
            </ul>
            <div className="mt-1 text-[11px] text-muted-foreground">Stage times are summed busy time; parallel searches overlap, so they can add up to more than the {sec(meta.wall_ms)} wall time. First token at {sec(meta.first_token_ms)}.</div>
          </div>
          <div>
            <div className="mb-1.5 font-medium text-fg-2">Models</div>
            <table className="w-full text-left tabular-nums">
              <thead className="text-muted-foreground">
                <tr><th className="pb-1 font-normal">Model</th><th className="pb-1 text-right font-normal">Prompt</th><th className="pb-1 text-right font-normal">Completion</th><th className="pb-1 text-right font-normal">Calls</th></tr>
              </thead>
              <tbody>
                {Object.entries(meta.usage).map(([m, [p, c, n]]) => (
                  <tr key={m} className="border-t border-border">
                    <td className="py-1 text-fg-2">{m}{meta.unpriced_models.includes(m) && <span className="ml-1.5 rounded border border-warning/40 px-1 text-[10px] text-warning">no price</span>}</td>
                    <td className="py-1 text-right">{p.toLocaleString()}</td>
                    <td className="py-1 text-right">{c.toLocaleString()}</td>
                    <td className="py-1 text-right">{n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[11px] text-muted-foreground">Trace <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-fg-2">{meta.trace_id}</code>, also in the server log and the <code className="font-mono">X-Trace-Id</code> response header.</div>
        </div>
      )}
    </div>
  );
}
