# Fathom — multi-agent RAG chat

Hybrid retrieval (Postgres FTS + pgvector, fused with RRF) → LLM reranker → ReAct-style agent loop
(decompose, parallel multi-hop search, reflect) → citation-grounded streaming answers, with a visible
reasoning trace in the UI and an offline evaluation harness.

```
ingest/      chunking, embeddings, upload pipeline (txt/md/pdf)
retrieval/   lexical.py (FTS) · dense.py (pgvector HNSW) · fuse.py (RRF) · rerank.py · search.py
agent/       loop.py — plan → parallel search → reflect → follow-up hop, emits trace events
generation/  prompt.py — citation-grounded answers ([1], [2]…)
api/         FastAPI + SSE streaming (/api/chat, /api/documents)
eval/        build_corpus.py, golden_set.json, scorer.py, run_eval.py, results/
web/         Next.js chat UI: streaming, clickable citations, reasoning-trace panel, upload
```

## Run

Needs `.env` with `OPENAI_API_KEY` and `DB_URL` (any Postgres with the `vector` extension).

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows path; use .venv/bin on Linux/macOS
python -m core.db --reset            # WARNING: drops the public schema, recreates Fathom's tables
python -m eval.build_corpus          # optional: regenerate fictional corpus + golden set
python -m ingest.pipeline data/corpus
uvicorn api.main:app --port 8000
cd web && npm install && npm run dev   # http://localhost:3000
```

Or `docker compose up` (local pgvector DB; needs `OPENAI_API_KEY` in the environment).
Search from the CLI: `python -m retrieval.search "your question" --rerank`.

Models: `gpt-6-luna` with `reasoning_effort=low` (generation, planning, reranking, judging) and `text-embedding-3-small`
(override with `CHAT_MODEL` / `REASONING_EFFORT` / `EMBED_MODEL`; the gpt-6 models reject `max_tokens` and custom temperature). The reranker is an LLM listwise reranker, not a BGE cross-encoder.

## Rate limiting and cost protection

Per-IP sliding-window limits on the paid endpoints, configured in `.env` (`0` disables a single limit):

| Variable | Default | Applies to |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | master switch |
| `RATE_LIMIT_CHAT_PER_MINUTE` | `6` | `POST /api/chat` per IP |
| `RATE_LIMIT_CHAT_PER_DAY` | `100` | `POST /api/chat` per IP per 24 h (the bill cap) |
| `RATE_LIMIT_UPLOAD_PER_HOUR` | `10` | `POST /api/documents` per IP |
| `RATE_LIMIT_GLOBAL_PER_MINUTE` | `120` | any `/api/*` request per IP |
| `MAX_QUESTION_CHARS` / `MAX_UPLOAD_MB` | `1000` / `10` | input size caps |
| `TRUST_PROXY` | `false` | read the client IP from `X-Forwarded-For` (only behind a proxy you control) |

Exceeded limits return `429` with `Retry-After`; the UI shows a friendly message. Counters are in-memory and
per process, so multiple workers/instances each keep their own (use Redis for a shared store). Behind a proxy without
`TRUST_PROXY=true` every user shares the proxy's IP and hits the limit together. These limits cap requests, not spend:
also set a monthly budget cap in the OpenAI dashboard.

## Evaluation

`python -m eval.run_eval --k 3` — 72 questions over 20 fictional documents (paired domains, so similar documents act as distractors), 19 of them multi-hop. Evidence is a verbatim quote; a chunk counts as a
hit if it contains the quote. Full results: [`eval/results/results.md`](eval/results/results.md).

| Stage | Recall@3 | Full-hit@3 | MRR | Retr. p50 / p95 ms |
|---|---|---|---|---|
| lexical (Postgres FTS) | 0.83 | 0.75 | 0.77 | 188 / 213 |
| dense (pgvector) | 0.78 | 0.71 | 0.74 | 830 / 1101 |
| hybrid (RRF) | 0.85 | 0.78 | 0.81 | 515 / 642 |
| hybrid + rerank | 0.94 | 0.90 | 0.92 | 2286 / 3754 |
| full pipeline + agent loop* | 0.94 | 0.89 | 0.88 | 2319 / 13490 |

Multi-hop questions only (Full-hit): hybrid 0.21 -> hybrid + rerank **0.63**; the agent loop adds nothing on top (0.58).
Generation (LLM-judged): answer accuracy 0.88 with and without the agent; unsupported-claim rate 0.010 / 0.013.
End-to-end p50 / p95: 3.2 s / 5.0 s (no agent), 3.5 s / 15.4 s (agent). First token p50 about 3.0-3.2 s.

Model comparison: an earlier run on `gpt-4o-mini` (kept in `eval/results/results_gpt-4o-mini.md`) showed reranking
with no lift (Full-hit 0.78 -> 0.79) and the agent loop helping multi-hop (0.21 -> 0.42). With `gpt-6-luna` the
reranker itself does the work and the agent loop is redundant, at much higher tail latency. Single runs of 72 questions.

Honest caveats:
- *Agent rows retrieve up to 8 chunks (merged sub-queries) and are scored over all of them, so they are not strictly
  K=3-comparable to the retrieval-only rows.
- Latency targets are not met: rerank adds about 1.7 s (target: retrieval + rerank under 400 ms), first token is about
  3 s (target 1.5 s), and multi-part questions reach p95 of 13-15 s. The DB is remote serverless Postgres and the eval
  runs 4 queries concurrently, which inflates latency.
- Golden questions and corpus are LLM-generated and the judge is the same model family as the generator. Treat numbers
  as relative comparisons between stages, not absolute quality.

## Known gaps / next steps
- Swap the LLM reranker for a local BGE cross-encoder to cut latency.
- No auth or multi-tenancy; upload/delete endpoints are unauthenticated (delete is not rate-limited beyond the global cap). CORS is `*` — restrict before deploying.
- Docker Compose files were written but not run in this environment (Docker Desktop was unavailable).
- No conversation persistence (history lives in the browser tab).
