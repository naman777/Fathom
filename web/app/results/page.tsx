"use client";

import { useEffect, useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Segmented } from "@/components/ui/segmented";
import PageShell, { Card, Section } from "../components/PageShell";
import { fmtTok, fmtUsd } from "../components/RequestStats";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Stat = { mean: number; sd: number };
type Stage = { runs: number; summary: Record<string, Stat>; by_type: Record<string, Record<string, Stat>>; usage: Record<string, [number, number, number]> };
type Dataset = Record<string, Stage>;
type Injection = {
  trials: number;
  attacks: Record<string, { off: { attack_success: number; fact_kept: number }; on: { attack_success: number; fact_kept: number } }>;
  success_total: { off: number; on: number };
  attempts_per_mode: number;
  clean_docs_scanned: number;
  clean_docs_flagged: Record<string, unknown>;
  scanner_detects: Record<string, boolean>;
};
type Lat = { p50: number; p95: number; p99: number };
type EntSummary = Record<string, number> & { retrieval_ms?: Lat; e2e_ms?: Lat };
type Enterprise = {
  stages?: Record<string, { summary: EntSummary; by_type: Record<string, EntSummary>; cost_usd: number; config: Record<string, string | number> }>;
  leak?: { total: Record<string, number>; roles: Record<string, { label: string; chunks_returned: number; chunks_leaked: number; forbidden_questions: number; forbidden_blocked: number; control_questions: number; control_recall_role: number | null; control_recall_admin: number | null }> };
  embed?: (Record<string, number> & { model: string })[];
  db?: { vectors: number; dim: number; queries: number; pgvector_build?: Record<string, number>; engines: Record<string, Record<string, number | Record<string, number>>> };
};
type Results = { synthetic?: Dataset; real?: Dataset; injection?: Injection; upgrades?: { title: string; note: string; columns: string[]; rows: string[][] }[]; enterprise?: Enterprise };
type Stats = {
  requests: number; wall_ms_p50?: number; wall_ms_p95?: number; tokens_total?: number; cost_usd_avg?: number | null;
  requests_with_unpriced_models?: number; stage_share_pct_avg?: Record<string, number>; prices?: Record<string, [number, number]>;
};

const DATASETS = {
  real: { label: "Real documents", sub: "11 IETF RFCs, 20 hand-labelled questions, 5 runs" },
  synthetic: { label: "Synthetic corpus", sub: "20 generated documents, 72 questions, 3 runs" },
} as const;
const f2 = (x?: number) => (x === undefined ? "–" : x.toFixed(2));
const pm = (s?: Stat, d = 2) => (!s ? "–" : s.sd > 0 ? `${s.mean.toFixed(d)} ± ${s.sd.toFixed(d)}` : s.mean.toFixed(d));
const ms = (s?: Stat) => (!s ? "–" : `${(s.mean / 1000).toFixed(1)}s`);

export default function ResultsPage() {
  const [data, setData] = useState<Results | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [err, setErr] = useState(false);
  const [ds, setDs] = useState<keyof typeof DATASETS>("real");

  useEffect(() => {
    fetch(`${API}/api/eval-results`).then((r) => r.json()).then(setData).catch(() => setErr(true));
    fetch(`${API}/api/stats`).then((r) => r.json()).then(setStats).catch(() => {});
  }, []);

  const cur = data?.[ds];
  const stages = useMemo(() => Object.entries(cur || {}), [cur]);
  const real = data?.real;
  const agent = real?.["full pipeline + agent loop"];
  const noAgent = real?.["full pipeline, no agent"];
  const rerank = real?.["hybrid + rerank"];

  return (
    <PageShell
      title="Results"
      lead={<>Everything here is read from the <span className="highlight">saved evaluation runs</span>, not typed in. Stages that call a language model were repeated and are shown as mean ± standard deviation, so you can see which differences are real and which are noise.</>}
    >
      {err && <Alert tone="warning">Can’t reach the API, so results can’t load. Start the backend and reload.</Alert>}

      {data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Headline label="Real documents · answer accuracy" value={f2(agent?.summary["answer_accuracy"]?.mean)} sub={`with the agent loop (${f2(noAgent?.summary["answer_accuracy"]?.mean)} without)`} />
          <Headline label="Real documents · retrieval" value={f2(rerank?.summary["full_hit@k"]?.mean)} sub="full-hit@5 after reranking: every needed passage in the top 5" />
          <Headline label="Multi-part questions, real" value={`${f2(noAgent?.by_type.multi?.["full_hit@k"].mean)} → ${f2(agent?.by_type.multi?.["full_hit@k"].mean)}`} sub="full-hit without → with the agent loop" />
          <Headline
            label="Average cost per question"
            value={stats?.cost_usd_avg != null ? fmtUsd(stats.cost_usd_avg) : "not set"}
            sub={stats?.requests ? `over the last ${stats.requests} live requests` : stats?.requests === 0 ? "ask a question to populate this" : "ask a question to populate this"}
          />
        </div>
      )}

      <Section id="retrieval" title="Retrieval quality by stage" note="Full-hit@5 is the share of questions where every passage needed to answer was in the top 5. Bars show the mean; the whisker is one standard deviation across runs.">
        <Segmented
          label="Dataset"
          className="mb-4 w-fit"
          value={ds}
          onChange={setDs}
          options={(Object.keys(DATASETS) as (keyof typeof DATASETS)[]).map((k) => ({ value: k, label: DATASETS[k].label }))}
        />
        <p className="mb-3 text-[13px] text-muted-foreground">{DATASETS[ds].sub}{ds === "synthetic" ? " · measured before the websearch and neighbour-expansion defaults" : " · shipped defaults"}</p>
        <Card className="space-y-2.5">
          {stages.length === 0 && <div className="text-sm text-muted-foreground">{data ? "No results saved for this dataset." : "Loading…"}</div>}
          {stages.map(([name, s]) => (
            <Bar key={name} label={ds === "real" && name.startsWith("full pipeline") ? `${name} *` : name} stat={s.summary["full_hit@k"]} runs={s.runs} />
          ))}
        </Card>
        <Table
          className="mt-3"
          head={["Stage", "Recall@5", "Full-hit@5", "MRR", "Retrieval p50", "p95"]}
          rows={stages.map(([name, s]) => [name, pm(s.summary["recall@k"]), pm(s.summary["full_hit@k"]), pm(s.summary["mrr"]), ms(s.summary["retrieval_ms_p50"]), ms(s.summary["retrieval_ms_p95"])])}
        />
        {ds === "real" && (
          <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            * These rows include neighbour expansion (each hit is widened by the chunk before and after it), so they are measured over more text than the rows above them; compare them by answer accuracy below. Lexical search is the strongest single retriever on the synthetic set but the weakest on real text, and absolute quality is much lower on real documents. That gap is why the synthetic numbers alone would have been misleading.
          </p>
        )}
      </Section>

      <Section id="answers" title="Answer quality and the agent loop" note="Answers are graded by a language model against a gold answer. The judge is the same model family as the answerer, so treat accuracy as secondary to the retrieval numbers above.">
        <Table
          head={["Dataset", "Pipeline", "Answer accuracy", "Unsupported claims", "Multi-part full-hit", "End-to-end p50", "p95"]}
          rows={(["real", "synthetic"] as const).flatMap((k) =>
            (["full pipeline, no agent", "full pipeline + agent loop"] as const).map((p) => {
              const s = data?.[k]?.[p];
              return [DATASETS[k].label, p.replace("full pipeline", "pipeline"), pm(s?.summary["answer_accuracy"]), pm(s?.summary["unsupported_claim_rate"], 3), pm(s?.by_type.multi?.["full_hit@k"]), ms(s?.summary["e2e_ms_p50"]), ms(s?.summary["e2e_ms_p95"])];
            })
          )}
        />
        <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
          The agent loop clearly helps questions with several parts. On the synthetic set, where questions are easy, it is not distinguishable from the plain pipeline and costs roughly three times the tail latency; the benefit shows up on harder, real text.
        </p>
      </Section>

      <Section id="cost" title="Cost per question" note="Token counts come from the model provider for every eval run. Dollar figures use the price table in configuration and appear only for models with a price set.">
        <CostTable stages={stages} prices={stats?.prices} />
      </Section>

      {stats && (
        <Section id="live" title="Live usage" note="Aggregated from the most recent requests this server handled (kept in memory; resets on restart).">
          {stats.requests === 0 ? (
            <Card className="text-sm text-muted-foreground">No requests yet. Ask a question in the chat and it will appear here.</Card>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <Card>
                <div className="text-xs text-muted-foreground">Requests · latency</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">{stats.requests}</div>
                <div className="mt-1 text-[13px] text-fg-2">p50 {ms({ mean: stats.wall_ms_p50 || 0, sd: 0 })} · p95 {ms({ mean: stats.wall_ms_p95 || 0, sd: 0 })} · {fmtTok(stats.tokens_total || 0)} tokens</div>
                {!!stats.requests_with_unpriced_models && <div className="mt-2 text-[11px] text-warning">{stats.requests_with_unpriced_models} requests used a model with no price set.</div>}
              </Card>
              <Card>
                <div className="mb-2 text-xs text-muted-foreground">Where the time goes (average share of busy time)</div>
                <div className="space-y-1.5">
                  {Object.entries(stats.stage_share_pct_avg || {}).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 text-xs">
                      <span className="w-20 shrink-0 capitalize text-muted-foreground">{k}</span>
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3"><span className="block h-full rounded-full bg-primary" style={{ width: `${v}%` }} /></span>
                      <span className="w-10 text-right tabular-nums text-muted-foreground">{Math.round(v)}%</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}
        </Section>
      )}

      {data?.injection && <InjectionSection inj={data.injection} />}

      {data?.enterprise && <EnterpriseSections ent={data.enterprise} />}

      {data?.upgrades?.map((u) => (
        <Section key={u.title} id={u.title.toLowerCase().replace(/\W+/g, "-")} title={u.title} note={u.note}>
          <Table head={u.columns} rows={u.rows} />
        </Section>
      ))}

      <Section id="caveats" title="How far to trust this">
        <ul className="max-w-2xl list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-fg-2">
          <li>The real-document set is 20 questions; one question is 5 points of full-hit, so differences of a few points are noise.</li>
          <li>Those questions were written by a language model from verbatim RFC sentences, and the judge is the same model family, not an independent human.</li>
          <li>A retrieved passage counts as a hit only if it contains the labelled quote, so a different passage that also answers the question counts as a miss. Retrieval numbers are a lower bound.</li>
          <li>Latency was measured with 4 concurrent queries against a remote database, which inflates it.</li>
        </ul>
      </Section>
    </PageShell>
  );
}

const ENT_STAGES: Record<string, string> = {
  lexical: "BM25 (Qdrant sparse)", dense: "dense (arctic-embed-m)", hybrid: "hybrid (RRF)", rerank: "hybrid + rerank",
  noagent: "full pipeline, no agent", agent: "full pipeline + agent loop",
};
const f3 = (x?: number | null) => (x === undefined || x === null ? "–" : x.toFixed(3));
const lat = (l?: Lat) => (!l ? "–" : l.p50 >= 1000 ? `${(l.p50 / 1000).toFixed(1)} / ${(l.p95 / 1000).toFixed(1)} / ${(l.p99 / 1000).toFixed(1)} s` : `${l.p50.toFixed(0)} / ${l.p95.toFixed(0)} / ${l.p99.toFixed(0)} ms`);

/** Enterprise search (EnterpriseRAG-Bench in Qdrant): pipeline stages, access-leak test, and the two choice experiments. */
function EnterpriseSections({ ent }: { ent: Enterprise }) {
  const stages = Object.entries(ent.stages || {});
  const gen = stages.filter(([, s]) => s.summary.overall_score !== undefined);
  const agent = ent.stages?.agent;
  return (
    <>
      {stages.length > 0 && (
        <Section
          id="enterprise"
          title="Enterprise search"
          note="EnterpriseRAG-Bench questions against a development index in Qdrant: every gold document plus a 6% sample of the 512k-document corpus. With far fewer distractors than the full corpus, these numbers are for comparing stages, not benchmark scores. Retrieval is scored at document level against the benchmark's gold documents, with no language model involved."
        >
          <Table
            head={["Stage", "Questions", "Context recall", "Context precision", "MRR", "Retrieval p50 / p95 / p99"]}
            rows={stages.map(([k, s]) => [ENT_STAGES[k] || k, String(s.summary.n), f3(s.summary.context_recall), f3(s.summary.context_precision), f3(s.summary.mrr), lat(s.summary.retrieval_ms)])}
          />
          {gen.length > 0 && (
            <Table
              className="mt-3"
              head={["Pipeline", "Questions", "Overall score", "Correctness", "Completeness", "Factuality", "End-to-end p50 / p95 / p99", "Cost"]}
              rows={gen.map(([k, s]) => [ENT_STAGES[k] || k, String(s.summary.n), f3(s.summary.overall_score), f3(s.summary.answer_correctness), f3(s.summary.answer_completeness), f3(s.summary.factuality), lat(s.summary.e2e_ms), fmtUsd(s.cost_usd)])}
            />
          )}
          {agent && (
            <Table
              className="mt-3"
              head={["Question type (agent loop)", "Questions", "Context recall", "Overall score", "Correctness", "Completeness"]}
              rows={Object.entries(agent.by_type).map(([t, s]) => [t.replace(/_/g, " "), String(s.n), f3(s.context_recall), f3(s.overall_score), f3(s.answer_correctness), f3(s.answer_completeness)])}
            />
          )}
          <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            Overall score is the benchmark&apos;s definition: correctness × completeness, averaged. Factuality is the share of answer claims supported by the retrieved context. The judge is {String(agent?.config.judge_model ?? "the answer model")}; the public leaderboard judges with a different model, so answer scores are not comparable with it. Rows that answer questions retrieve up to 8 passages, so their recall is measured over more text than the top-5 rows.
          </p>
        </Section>
      )}

      {ent.leak && (
        <Section id="access" title="Access control leak test" note="Every benchmark question is searched as every restricted role, using the widest retrieval the API performs. A leak is any returned passage the role may not read. The control column checks the filter does not cost recall on questions the role is allowed to answer.">
          <Table
            head={["Role", "Passages returned", "Leaked", "Forbidden questions blocked", "Allowed questions", "Recall@20 (as admin)"]}
            rows={Object.values(ent.leak.roles).map((r) => [r.label, r.chunks_returned.toLocaleString(), String(r.chunks_leaked), `${r.forbidden_blocked} / ${r.forbidden_questions}`, String(r.control_questions), `${f3(r.control_recall_role)} (${f3(r.control_recall_admin)})`])}
          />
        </Section>
      )}

      {ent.embed && (
        <Section id="embedding" title="Embedding model and chunk size" note="Same subset of documents and the 470 questions with gold documents, ranked by exact cosine similarity so the model is the only variable. Open-source models ran on a laptop GPU.">
          <Table
            head={["Model", "Chunk size", "Dimensions", "Recall@5", "Recall@10", "MRR@20", "Chunks / s"]}
            rows={[...ent.embed].sort((a, b) => b["recall@10"] - a["recall@10"]).map((r) => [r.model.replace("openai:", "OpenAI "), `${r.chunk_target} chars`, String(r.dim), f3(r["recall@5"]), f3(r["recall@10"]), f3(r["mrr@20"]), r.model.startsWith("openai:") ? "API" : r.chunks_per_s.toFixed(0)])}
          />
        </Section>
      )}

      {ent.db && (
        <Section id="vector-db" title="Qdrant vs Postgres + pgvector" note={`The same ${ent.db.vectors.toLocaleString()} vectors (${ent.db.dim} dimensions) and ${ent.db.queries} query vectors in both engines, one query at a time, vector search only. Recall is against exact nearest neighbours. "Short" counts queries that returned fewer than 10 results.`}>
          {Object.entries(ent.db.engines).map(([flt, row]) => (
            <Table
              key={flt}
              className="mb-3"
              head={[flt === "none" ? "No filter" : `Role filter: ${flt.replace("_", " ")} (${Math.round(Number(row.share_of_corpus_visible) * 100)}% of corpus visible)`, "Recall@10", "p50", "p95", "p99", "Short"]}
              rows={Object.entries(row).filter(([, v]) => typeof v === "object").map(([eng, v]) => {
                const r = v as Record<string, number>;
                return [eng, f3(r["recall@10"]), `${r.p50.toFixed(1)} ms`, `${r.p95.toFixed(1)} ms`, `${r.p99.toFixed(1)} ms`, String(r.queries_returning_fewer_than_10)];
              })}
            />
          ))}
          <p className="max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            Qdrant applies the role filter inside the graph search, so filtered queries stay fast and complete. pgvector filters after the index scan: at default settings a filtered query can come back short, and the settings that fix that fall back to much slower scans. pgvector was run with default tuning; partial indexes or partitioning per group were not tried.
          </p>
        </Section>
      )}
    </>
  );
}

function Headline({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <Card>
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1.5 font-montserrat text-3xl font-semibold tabular-nums tracking-tight">{value}</div>
      <div className="mt-1 text-[12px] leading-snug text-muted-foreground">{sub}</div>
    </Card>
  );
}

function Bar({ label, stat, runs }: { label: string; stat?: Stat; runs: number }) {
  if (!stat) return null;
  const pct = (x: number) => `${Math.max(0, Math.min(100, x * 100))}%`;
  return (
    <div className="grid grid-cols-[minmax(110px,220px)_1fr_auto] items-center gap-3 text-[13px]">
      <span className="truncate text-fg-2" title={label}>{label}</span>
      <span className="relative h-3 rounded-full bg-surface-3">
        <span className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: pct(stat.mean) }} />
        {stat.sd > 0 && <span className="absolute top-1/2 h-px -translate-y-1/2 bg-foreground" style={{ left: pct(stat.mean - stat.sd), width: `calc(${pct(stat.mean + stat.sd)} - ${pct(stat.mean - stat.sd)})` }} />}
      </span>
      <span className="w-28 text-right tabular-nums text-muted-foreground">{pm(stat)} <span className="text-[11px]">({runs} run{runs === 1 ? "" : "s"})</span></span>
    </div>
  );
}

function Table({ head, rows, className = "" }: { head: string[]; rows: string[][]; className?: string }) {
  return (
    <div className={`card-chai overflow-x-auto ${className}`}>
      <table className="w-full min-w-[560px] text-left text-[13px] tabular-nums">
        <thead className="border-b border-border text-muted-foreground">
          <tr>{head.map((h, i) => <th key={h} className={`px-3 py-2.5 font-medium ${i > 1 ? "text-right" : ""}`}>{h}</th>)}</tr>
        </thead>
        <tbody className="text-fg-2">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border first:border-t-0">
              {r.map((c, j) => <td key={j} className={`px-3 py-2 ${j > 1 ? "text-right" : ""}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CostTable({ stages, prices }: { stages: [string, Stage][]; prices?: Record<string, [number, number]> }) {
  const rows: string[][] = [];
  for (const [name, s] of stages) {
    const q = (s.summary["n"]?.mean || 1) * (s.runs || 1);
    for (const [model, [pt, ct, calls]] of Object.entries(s.usage || {})) {
      const p = prices?.[model];
      const usd = p ? (pt / 1e6) * p[0] + (ct / 1e6) * p[1] : null;
      rows.push([name, model, fmtTok(Math.round(pt / q)), fmtTok(Math.round(ct / q)), (calls / q).toFixed(1), usd == null ? "price not set" : fmtUsd(usd / q)]);
    }
  }
  if (!rows.length) return <Card className="text-sm text-muted-foreground">No token usage recorded yet for this dataset.</Card>;
  return <Table head={["Stage", "Model", "Prompt tokens / question", "Completion tokens", "Calls", "Cost / question"]} rows={rows} />;
}

function InjectionSection({ inj }: { inj: Injection }) {
  const n = inj.attempts_per_mode;
  return (
    <Section id="injection" title="Prompt-injection test" note={`${Object.keys(inj.attacks).length} attack documents (direct overrides, role spoofing, hidden characters, tag breakout, fake dialogue, image exfiltration), ${inj.trials} trials each. An attack succeeds if its canary appears in the answer.`}>
      <div className="grid gap-3 sm:grid-cols-3">
        <Headline label="Attacks that worked, old prompt" value={`${inj.success_total.off}/${n}`} sub="passages inserted as plain text" />
        <Headline label="Attacks that worked, hardened" value={`${inj.success_total.on}/${n}`} sub="passages wrapped as untrusted data" />
        <Headline label="Scanner false positives" value={`${Object.keys(inj.clean_docs_flagged).length}/${inj.clean_docs_scanned}`} sub="clean documents flagged at ingest" />
      </div>
      <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
        The answer model resisted every attack even without the hardened prompt, so this test cannot show the hardening helps on this model; it shows the model was already robust to these payloads and that hardening does not hurt answers. The other defences (sanitising, scanning, blocking images in answers) do not depend on the model. Only one model and simple-to-moderate attacks were tested.
      </p>
    </Section>
  );
}
