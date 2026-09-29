import type { Metadata } from "next";
import PageShell, { Card, Section } from "../components/PageShell";

export const metadata: Metadata = { title: "Architecture — Fathom", description: "How Fathom ingests, retrieves, reasons over and answers from your documents." };

const FLOW = [
  { t: "Question", d: "Up to 1,000 characters, with the last 6 chat turns", tone: "io" },
  { t: "Plan", d: "Multi-part questions are split into up to 4 standalone searches; simple ones skip this call", tone: "llm" },
  { t: "Hybrid search", d: "Postgres full-text + pgvector, in parallel per sub-question, fused with Reciprocal Rank Fusion", tone: "db" },
  { t: "Rerank", d: "An LLM scores the top 20 fused passages 0–9 in one call; the best 5 are kept", tone: "llm" },
  { t: "Reflect", d: "Is every entity in the question covered? If not, a follow-up search (one by default, configurable)", tone: "llm" },
  { t: "Evidence", d: "De-duplicated and capped at 8 passages, optionally widened with neighbouring chunks", tone: "db" },
  { t: "Answer", d: "Streams a cited answer that may use only the numbered sources", tone: "llm" },
];
const tone: Record<string, string> = {
  io: "border-border-strong bg-surface-2",
  llm: "border-accent/40 bg-accent-soft",
  db: "border-success/40 bg-success/10",
};

function Pill({ children }: { children: React.ReactNode }) {
  return <span className="rounded-md bg-surface-3 px-1.5 py-0.5 font-mono text-[12px] text-fg-2">{children}</span>;
}

export default function Architecture() {
  return (
    <PageShell
      title="Architecture"
      lead="Fathom is a retrieval-augmented chat system: it finds the passages in your documents that bear on a question, reasons about whether it has enough, and writes an answer that cites where each claim came from. Every stage is measured, so the trade-offs below have numbers behind them."
    >
      <Section id="flow" title="What happens to a question" note="Green stages run in Postgres, purple stages call a language model. The agent loop (plan, reflect, follow-up) can be switched off in the sidebar.">
        <ol className="grid gap-2.5 sm:grid-cols-2">
          {FLOW.map((s, i) => (
            <li key={s.t} className={`flex gap-3 rounded-xl border p-3.5 ${tone[s.tone]} ${i === FLOW.length - 1 ? "sm:col-span-2" : ""}`}>
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-bg text-xs font-semibold text-fg-2">{i + 1}</span>
              <div>
                <div className="text-sm font-semibold">{s.t}</div>
                <div className="mt-0.5 text-[13px] leading-relaxed text-fg-2">{s.d}</div>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-[13px] text-muted">
          Every request gets a trace id, stage timings, token counts and a dollar estimate, shown under each answer and written to the server log as one JSON line.
        </p>
      </Section>

      <Section id="ingest" title="Ingestion and storage">
        <div className="grid gap-3 sm:grid-cols-2">
          <Card>
            <div className="text-sm font-semibold">Ingestion</div>
            <ul className="mt-2 space-y-1.5 text-[13px] leading-relaxed text-fg-2">
              <li>Reads <Pill>.txt</Pill> <Pill>.md</Pill> <Pill>.pdf</Pill>; the original is kept in S3 when configured.</li>
              <li>Splits along paragraph, then sentence boundaries into ~900-character chunks with 150 characters of overlap.</li>
              <li>Embeds chunks in batches with <Pill>text-embedding-3-small</Pill> (1536 dimensions).</li>
              <li>Scans the text for instruction-like content and flags the document (see Security).</li>
              <li>Optional contextual headers: each chunk is prefixed with its document description and nearest heading.</li>
            </ul>
          </Card>
          <Card>
            <div className="text-sm font-semibold">One Postgres database</div>
            <ul className="mt-2 space-y-1.5 text-[13px] leading-relaxed text-fg-2">
              <li><Pill>documents</Pill>: title, source, S3 key, ingest scan flags.</li>
              <li><Pill>chunks</Pill>: content, a <Pill>vector(1536)</Pill> embedding, and a generated <Pill>tsvector</Pill>.</li>
              <li>HNSW index (cosine) for vectors, GIN index for full-text, cascade delete from document to chunks.</li>
              <li>Both retrieval paths and the metadata live in one place, so a delete is one statement and there is no index to keep in sync.</li>
            </ul>
          </Card>
        </div>
      </Section>

      <Section id="retrieval" title="Retrieval" note="Three ideas, each kept because it measurably helped: search two ways, rerank a wide pool, and let an agent loop handle questions with several parts.">
        <div className="grid gap-3 sm:grid-cols-3">
          <Card>
            <div className="text-sm font-semibold">Hybrid search</div>
            <p className="mt-2 text-[13px] leading-relaxed text-fg-2">Full-text catches exact names and numbers; vectors catch paraphrase. Their ranked lists (20 each) are merged with Reciprocal Rank Fusion, which needs no score calibration.</p>
          </Card>
          <Card>
            <div className="text-sm font-semibold">LLM reranker</div>
            <p className="mt-2 text-[13px] leading-relaxed text-fg-2">One call scores the top 20 candidates. The pool size matters: on real documents the right passage was in the top 8 only 45% of the time, and widening to 20 lifted full-hit from 0.45 to about 0.65.</p>
          </Card>
          <Card>
            <div className="text-sm font-semibold">Agent loop</div>
            <p className="mt-2 text-[13px] leading-relaxed text-fg-2">Splits multi-part questions, searches in parallel, checks that every entity has evidence, and follows up. On real text it lifts multi-part full-hit from 0.36 to 0.72.</p>
          </Card>
        </div>
      </Section>

      <Section id="models" title="Models and what they cost" note="Cost per request is computed from provider-reported token counts and the price table in configuration. Models without a configured price show tokens only.">
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[520px] text-left text-[13px]">
            <thead className="border-b border-border text-muted">
              <tr><th className="px-4 py-2.5 font-medium">Role</th><th className="px-4 py-2.5 font-medium">Default model</th><th className="px-4 py-2.5 font-medium">Setting</th></tr>
            </thead>
            <tbody className="text-fg-2">
              {[
                ["Answer", "gpt-6-luna", "CHAT_MODEL"],
                ["Rerank", "gpt-6-luna", "RERANK_MODEL"],
                ["Plan and reflect", "gpt-6-luna", "PLANNER_MODEL"],
                ["Embeddings", "text-embedding-3-small", "EMBED_MODEL"],
                ["Eval judge", "same as answer model", "JUDGE_MODEL"],
              ].map(([a, b, c]) => (
                <tr key={a} className="border-t border-border first:border-t-0">
                  <td className="px-4 py-2.5">{a}</td>
                  <td className="px-4 py-2.5 font-mono text-[12px]">{b}</td>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-muted">{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-muted">
          Reasoning models spend hidden tokens and time. In the breakdown under an answer, reranking with <Pill>gpt-6-luna</Pill> is typically the largest single stage; a small non-reasoning model was faster and about as accurate on the real-document test (see Results).
        </p>
      </Section>

      <Section id="security" title="Security: documents are untrusted input" note="Anything a user uploads ends up inside prompts, so a poisoned document can try to give the model orders. The threat model and the defences:">
        <div className="grid gap-3 sm:grid-cols-2">
          <Card>
            <div className="text-sm font-semibold">Threats considered</div>
            <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[13px] leading-relaxed text-fg-2">
              <li>Instructions hidden in a document (“ignore previous instructions…”).</li>
              <li>Breaking out of the source frame with fake closing tags or chat markup.</li>
              <li>Invisible characters used to slip past filters.</li>
              <li>Data exfiltration through an image or link the model is told to print.</li>
              <li>Manipulating the reranker or reflector, which also read passages.</li>
            </ul>
          </Card>
          <Card>
            <div className="text-sm font-semibold">Defences</div>
            <ul className="mt-2 list-disc space-y-1.5 pl-4 text-[13px] leading-relaxed text-fg-2">
              <li>Passages are wrapped as data in every prompt, with explicit rules that sources are never instructions.</li>
              <li>Hidden characters are stripped and our own delimiter tags are neutralised.</li>
              <li>An ingest scan flags instruction-like documents (warning icon in the document list). It reports; it does not block.</li>
              <li>Answers cannot render images, and only plain web links are clickable.</li>
              <li>The model has no tools or actions, so the worst case is a wrong answer, not a side effect.</li>
            </ul>
          </Card>
        </div>
        <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-muted">
          Honest limits: prompt-level defences are not guarantees, and the API has no user authentication, so do not expose an instance that holds private documents without an authentication layer in front of it. Measured attack results are on the Results page.
        </p>
      </Section>

      <Section id="stack" title="Stack">
        <div className="flex flex-wrap gap-2 text-[13px]">
          {["Next.js 16 + Tailwind v4", "FastAPI + Server-Sent Events", "Postgres + pgvector (Neon)", "Reciprocal Rank Fusion", "OpenAI models", "S3 for originals", "pytest, 80+ tests, no network"].map((x) => (
            <span key={x} className="rounded-full border border-border bg-surface px-3 py-1 text-fg-2">{x}</span>
          ))}
        </div>
      </Section>
    </PageShell>
  );
}
