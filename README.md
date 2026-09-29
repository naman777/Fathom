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

Models (all overridable in `.env`, see `.env.example`):

| Task | Default | Variable |
|---|---|---|
| Answers, judging | `gpt-6-luna` (`reasoning_effort=low`) | `CHAT_MODEL`, `REASONING_EFFORT` |
| Reranking | `gpt-4.1-mini` | `RERANK_MODEL` |
| Query planning / reflection | `gpt-4.1-mini` | `PLANNER_MODEL` |
| Embeddings | `text-embedding-3-small` | `EMBED_MODEL` |

The gpt-5/6 families reject `max_tokens` and custom temperature; `core/llm.py` picks the right parameters per model family.
`RERANKER=local` switches to an ONNX cross-encoder (`pip install fastembed`, model via `LOCAL_RERANK_MODEL`) that needs no API call.

Tests: `python -m pytest -q` (19 tests: rate limiter, input caps, admin auth, CORS, chunking, RRF, scorer; none call OpenAI).

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
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | allowed browser origins (`*` = any, dev only) |
| `ADMIN_TOKEN` | empty | if set, upload/delete require header `X-Admin-Token` (the UI prompts for it); chat stays public |

Exceeded limits return `429` with `Retry-After`; the UI shows a friendly message. Counters are in-memory and
per process, so multiple workers/instances each keep their own (use Redis for a shared store). Behind a proxy without
`TRUST_PROXY=true` every user shares the proxy's IP and hits the limit together. These limits cap requests, not spend:
also set a monthly budget cap in the OpenAI dashboard.

## Evaluation

`python -m eval.run_eval --k 3` runs 72 questions over 20 fictional documents (paired domains, so similar documents act
as distractors), 19 of them multi-hop. Evidence is a verbatim quote; a chunk counts as a hit if it contains the quote.
Full results: [`eval/results/results.md`](eval/results/results.md).

| Stage | Recall@3 | Full-hit@3 | MRR | Retr. p50 / p95 ms |
|---|---|---|---|---|
| lexical (Postgres FTS) | 0.83 | 0.75 | 0.77 | 168 / 198 |
| dense (pgvector) | 0.78 | 0.71 | 0.74 | 770 / 1116 |
| hybrid (RRF) | 0.85 | 0.78 | 0.81 | 437 / 671 |
| hybrid + rerank (`gpt-4.1-mini`) | 0.91 | 0.86 | 0.87 | 1343 / 1670 |
| full pipeline + agent loop* | 0.94 | 0.90 | 0.86 | 1405 / 7744 |

| Generation | Answer accuracy | Unsupported-claim rate | First token p50 / p95 ms | End-to-end p50 / p95 ms |
|---|---|---|---|---|
| no agent | 0.83 | 0.026 | 2274 / 3062 | 2544 / 3731 |
| with agent loop | 0.92 | 0.014 | 2258 / 8631 | 2517 / 9496 |

Multi-hop questions only (Full-hit@3): hybrid 0.21, hybrid + rerank 0.47, agent loop **0.63**.

### Reranker comparison (full-hit@3, 72 questions, sequential; `python -m eval.bench_rerank`)

| Reranker | Full-hit@3 | MRR | Latency p50 |
|---|---|---|---|
| none (hybrid RRF) | 0.78 | 0.81 | ~0.4 s |
| local MiniLM-L6 cross-encoder (10 cand.) | 0.79 | 0.85 | 0.58 s |
| local BGE-reranker-base (10 cand.) | 0.81 | 0.82 | 2.0 s |
| LLM `gpt-4.1-nano` | 0.78 | 0.81 | ~1.8 s* |
| **LLM `gpt-4.1-mini` (default)** | 0.85 | 0.89 | ~1.5 s* |
| LLM `gpt-6-luna` | 0.86 | 0.88 | ~2.2 s* |

*measured with 4 concurrent queries, so somewhat inflated. The local rerankers are fast but barely beat no reranking on
this data; the LLM reranker is the only one giving a real lift, at about +0.9 s.

### Answer-model comparison (with agent loop)
`gpt-6-luna`: accuracy 0.92, unsupported-claim rate 1.4%. `gpt-4.1-mini`: accuracy 0.96, unsupported 3.2%, first token
only ~0.2 s faster (retrieval dominates). `gpt-6-luna` is kept as the default because groundedness matters most for RAG.
Earlier runs with every stage on `gpt-6-luna` or `gpt-4o-mini` are kept in `eval/results/` for reference.

Honest caveats:
- *Agent rows retrieve up to 8 chunks (merged sub-queries) and are scored over all of them, so they are not strictly
  K=3-comparable to the retrieval-only rows.
- Latency targets are still not met: hybrid + rerank is about 1.3 s (target 400 ms), first token about 2.3 s (target
  1.5 s), and multi-part questions with the agent reach p95 of about 8-10 s. The DB is remote serverless Postgres and the
  eval runs 4 queries concurrently, which inflates latency.
- Golden questions and corpus are LLM-generated, and the judge is the same model family as the generator. Treat numbers
  as relative comparisons between stages. Single runs of 72 questions: differences of a few points are within noise
  (the same reranker config scored 0.86-0.90 across runs).

## Known gaps / next steps
- Latency targets (see caveats). Ideas: a stronger local reranker on GPU, co-locating the DB with the API, streaming the
  first tokens before reranking finishes.
- Rate-limit counters are in-memory and per process; use a shared store (Redis) if you run several instances.
- Auth is a single shared `ADMIN_TOKEN` for document changes; there are no user accounts or per-user documents.
- Chat history is stored only in the browser (localStorage), not on the server.
- Docker Compose validates (`docker compose config`) but the images were never built or run: the Docker engine would not
  start on the development machine. Treat it as untested.
- Not deployed. No public demo link yet (needs a hosting account: Fly.io / Render for the API, Vercel for `web/`).
- Evaluation uses a synthetic corpus; a real-world corpus would be a better test.
