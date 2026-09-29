# Fathom

**Chat with your documents.** Fathom is a retrieval-augmented (RAG) chat platform: you upload documents, ask questions in
natural language, and get streamed answers that cite the exact passages they came from, along with a visible trace of how
the answer was found. It ships with an offline evaluation harness so retrieval and answer quality are measured, not
assumed.

```
question -> [planner] -> parallel hybrid search (Postgres full-text + pgvector, fused with RRF)
         -> LLM reranker -> [reflect: is the evidence enough? follow up once if not]
         -> citation-grounded streaming answer  ->  chat UI (citations, sources, reasoning trace)
```

**Status:** working end to end (backend, UI, eval, tests, one-command launcher). Not deployed, and Docker is untested.
See [Status](#status-done-and-pending) for the full done/pending list and [Evaluation](#evaluation) for measured results
and honest caveats.

---

## Contents
1. [Features](#features)
2. [How it works](#how-it-works)
3. [Tech stack](#tech-stack)
4. [Repository layout](#repository-layout)
5. [Quick start](#quick-start)
6. [Configuration](#configuration)
7. [API reference](#api-reference)
8. [Web UI](#web-ui)
9. [Security and cost protection](#security-and-cost-protection)
10. [Evaluation](#evaluation)
11. [Tests](#tests)
12. [Status: done and pending](#status-done-and-pending)
13. [Deviations from the original plan](#deviations-from-the-original-plan)

---

## Features

- **Ingestion** of `.txt`, `.md` and `.pdf` files (upload in the UI or bulk-load from a folder), with paragraph/sentence-aware
  chunking and batched embeddings.
- **Hybrid retrieval**: Postgres full-text search *and* pgvector cosine search, merged with Reciprocal Rank Fusion.
- **Reranking** of the fused candidates by an LLM listwise reranker (or an optional local ONNX cross-encoder).
- **Agent loop**: decomposes multi-part questions into sub-queries, searches them in parallel, checks whether the evidence
  is sufficient, and makes one follow-up search if something is missing. Every step is streamed to the UI as a trace.
- **Citation-grounded answers** (`[1]`, `[2]`...) that answer only from retrieved sources and say so when the sources do not
  contain the answer.
- **Streaming chat UI** (Next.js): live reasoning trace, markdown answers, clickable citation chips, source cards and a
  source drawer, light/dark theme, saved chat history, drag-and-drop upload, stop button, mobile layout.
- **Cost and abuse protection**: per-IP rate limits (per minute, per day, uploads, deletes), input-size caps, configurable
  CORS. All tunable from `.env`.
- **Evaluation harness**: 72 golden questions (19 multi-hop) scored for Recall@K, Full-hit@K, Precision@K, MRR, answer
  accuracy, unsupported-claim rate and latency (p50/p95), stage by stage.
- **One-command launcher** (`python run.py`) and a 19-test pytest suite.

## How it works

### 1. Ingestion (`ingest/`)
Text is read from the file (PDFs via `pypdf`), split into chunks of about 900 characters along paragraph then sentence
boundaries with 150 characters of overlap, embedded with `text-embedding-3-small` (1536 dimensions, in batches of 96), and
stored. Each document is a row in `documents`; each chunk a row in `chunks`.

### 2. Storage (`core/db.py`)
One Postgres database holds both indexes:

| Table | Columns of note | Indexes |
|---|---|---|
| `documents` | `id`, `title`, `source`, `created_at` | primary key |
| `chunks` | `document_id` (cascade delete), `position`, `content`, `embedding vector(1536)`, `tsv tsvector` (generated from `content`) | GIN on `tsv`, HNSW (cosine) on `embedding`, btree on `document_id` |

### 3. Hybrid retrieval (`retrieval/`)
- `lexical.py`: Postgres full-text search (`ts_rank_cd`) with OR semantics so long natural-language questions still match.
- `dense.py`: cosine similarity over the HNSW index; query embeddings are cached in-process so repeat queries are free.
- `fuse.py`: Reciprocal Rank Fusion (`k=60`) over the two ranked lists of 20 candidates each.
- `rerank.py`: the top 8 fused candidates are scored 0-9 in **one** short LLM call (default `gpt-4.1-mini`); the best `k`
  are kept. `rerank_local.py` is an optional API-free alternative (see [Configuration](#configuration)).
- `search.py`: `hybrid(...)` ties it together and also exposes `lexical`-only and `dense`-only modes for evaluation. CLI:
  `python -m retrieval.search "your question" --rerank`.

### 4. Agent loop (`agent/loop.py`)
1. **Plan**: a cheap heuristic decides whether the question looks multi-part ("compare", "and", commas, "both"...). If yes
   (or if there is chat history), the planner model splits it into up to 4 standalone sub-queries; otherwise the question
   is searched as-is and no planner call is spent.
2. **Search**: sub-queries run in parallel, each through hybrid search + rerank.
3. **Reflect** (multi-part questions only): a model checks that every entity in the question has evidence; if not, it
   proposes one single-topic follow-up query, which is searched once.
4. **Evidence**: results are de-duplicated and capped at the 8 best chunks, which become numbered sources.

The loop yields trace events (`plan`, `search`, `results`, `reflect`, `sources`), which the API forwards to the UI.

### 5. Generation (`generation/prompt.py`)
The answer model sees only the numbered sources (plus up to the last 6 chat turns) and is instructed to cite every claim
and to admit when the sources do not contain the answer. Tokens are streamed.

### 6. Streaming API (`api/main.py`)
`POST /api/chat` returns Server-Sent Events: `trace`, `retrieval_done`, `first_token`, `token`, `done`, `error`. The UI
renders the trace live and appends tokens as they arrive; timing (retrieval, first token, total) is reported per answer.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16 (App Router), React, Tailwind CSS v4, `react-markdown` + GFM. Custom chat UI (no chat framework) |
| API | Python 3.12, FastAPI, Uvicorn, Server-Sent Events |
| Database | Postgres with `pgvector` (developed against Neon); built-in full-text search for lexical retrieval |
| Fusion / rerank | Reciprocal Rank Fusion; LLM listwise reranker (default) or local ONNX cross-encoder (`fastembed`, optional) |
| LLMs | OpenAI: answers `gpt-6-luna`, rerank/planner `gpt-4.1-mini`, embeddings `text-embedding-3-small` |
| Eval | Python scripts, LLM-generated corpus and golden set, LLM judge for accuracy and groundedness |
| Tests | pytest (FastAPI `TestClient`) |
| Packaging | `run.py` launcher; Dockerfiles and `docker-compose.yml` (untested) |

## Repository layout

```
run.py, run.bat      one-command launcher (setup, health checks, clean shutdown)
core/                config.py (env), llm.py (OpenAI wrapper), db.py (schema), ratelimit.py (per-IP limiter)
ingest/              chunking.py, pipeline.py (CLI: python -m ingest.pipeline [path])
retrieval/           lexical.py, dense.py, fuse.py, rerank.py, rerank_local.py, search.py
agent/               loop.py (plan -> parallel search -> reflect -> follow-up)
generation/          prompt.py (grounded prompts, blocking and streaming)
api/                 main.py (FastAPI: chat SSE, documents CRUD, health)
eval/                build_corpus.py, golden_set.json, scorer.py, run_eval.py, bench_rerank.py, real_corpus.py,
                     build_real_golden.py, real_golden_set.json, results/
tests/               test_api_protection.py, test_retrieval_logic.py
web/                 Next.js app (app/page.tsx, app/components/{Assistant,icons,types})
data/corpus/         20 generated fictional documents used for the demo and evaluation
Dockerfile, web/Dockerfile, docker-compose.yml, .dockerignore   container build (untested)
PLAN.md, progress.md, "Multi-Agent RAG Chat Platform — Build Plan.md"   planning and progress log
```

## Quick start

Requirements: **Python 3.10+**, **Node.js 20+**, an **OpenAI API key**, and a **Postgres database with the `pgvector`
extension** (a free Neon database works). Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` and `DB_URL`.

### One command

```bash
python run.py          # Windows: run.bat
```

On first run it creates `.venv` and installs dependencies, runs `npm install`, ensures the DB schema exists (it never drops
data by itself), offers to ingest the sample corpus when the database is empty, starts the API (`:8000`) and web UI
(`:3000`), waits until both are healthy, opens the browser, and stops both cleanly on Ctrl+C.

| Flag | Effect |
|---|---|
| `--seed` | ingest `data/corpus` if the DB has no documents, without prompting (calls the embeddings API) |
| `--prod` | `next build` + `next start` instead of the dev server |
| `--no-web` / `--no-open` | API only / don't open the browser |
| `--test` | run the test suite and exit |
| `--eval` | run the evaluation harness and exit |
| `--reset` | **drop every table** in the DB's public schema and recreate them (asks for confirmation) |
| `--api-port N` / `--web-port N` | change ports |

Verified on Windows only; `--reset`, `--prod` and a clean-machine first run have not been exercised.

### Manual steps

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt    # Linux/macOS: .venv/bin/pip
python -m core.db --reset          # WARNING: drops the public schema, recreates Fathom's tables
python -m ingest.pipeline data/corpus
uvicorn api.main:app --port 8000
cd web && npm install && npm run dev      # http://localhost:3000
```

### Docker (untested)
`docker compose up` is defined for a local pgvector DB, the API and the web app. `docker compose config` validates, but the
images were never built or run because the Docker engine would not start on the development machine.

## Configuration

Everything is read from `.env` (see `.env.example`). Only the first two are required.

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | required | OpenAI access |
| `DB_URL` | required | Postgres connection string (needs the `vector` extension) |
| `CHAT_MODEL` | `gpt-6-luna` | answer model (also used by the eval judge) |
| `REASONING_EFFORT` | `low` | for gpt-5/6/o-series models |
| `RERANK_MODEL` | `gpt-4.1-mini` | LLM reranker |
| `PLANNER_MODEL` | `gpt-4.1-mini` | query decomposition and reflection |
| `EMBED_MODEL` | `text-embedding-3-small` | embeddings (schema is fixed at 1536 dimensions) |
| `RERANKER` | `llm` | `llm` or `local` (ONNX cross-encoder via `pip install fastembed`; no API call) |
| `LOCAL_RERANK_MODEL`, `LOCAL_RERANK_CANDIDATES` | MiniLM-L-12, `20` | settings for the local reranker |
| `RATE_LIMIT_ENABLED` | `true` | master switch for rate limiting |
| `RATE_LIMIT_CHAT_PER_MINUTE` / `_PER_DAY` | `6` / `100` | chat requests per IP |
| `RATE_LIMIT_UPLOAD_PER_HOUR` / `_DELETE_PER_HOUR` | `10` / `20` | document changes per IP |
| `RATE_LIMIT_GLOBAL_PER_MINUTE` | `120` | any `/api/*` request per IP |
| `MAX_QUESTION_CHARS` / `MAX_UPLOAD_MB` | `1000` / `10` | input size caps |
| `TRUST_PROXY` | `false` | read client IP from `X-Forwarded-For` (only behind a proxy you control) |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | allowed browser origins (`*` = any, dev only) |

`0` disables an individual rate limit. The gpt-5/6 model families reject `max_tokens` and custom temperature;
`core/llm.py` chooses the correct parameters per model family automatically.

## API reference

| Method and path | Description |
|---|---|
| `GET /api/health` | liveness + DB check |
| `GET /api/documents` | list documents with chunk counts |
| `POST /api/documents` | upload a `.txt`/`.md`/`.pdf` (multipart field `file`); stored in S3 when `AWS_S3_BUCKET` is set |
| `DELETE /api/documents/{id}` | delete a document and its chunks (rate limited, no authentication) |
| `POST /api/chat` | body `{question, history?, agent?, rerank?}`; responds with an SSE stream |

Chat SSE events: `trace` (plan / search / results / reflect / sources), `retrieval_done`, `first_token`, `token`, `done`,
`error`. Errors: `400` empty question / bad file type, `413` input too large, `429` rate limited
(with `Retry-After` and a JSON `detail`).

## Web UI

- **Chat**: streaming markdown answers, inline citation chips that open the source in a side drawer, source cards under
  each answer, timing (retrieval / first token / total), copy button, stop-generation button.
- **Reasoning trace**: live progress ("Planning searches...", "Searching: ...") that folds into a summary such as
  "Reasoned in 3 searches" and can be expanded to show the plan, each query, passages retrieved and the reflection result.
- **Sidebar**: knowledge-base list with drag-and-drop upload and delete, saved **History** (stored in this browser's
  `localStorage`, last 30 chats), and switches for the agent loop and reranker.
- **Polish**: light/dark theme with saved preference, responsive layout with a slide-in sidebar on mobile, friendly
  rate-limit and error messages with a retry countdown.

## Security and cost protection

- **Per-IP sliding-window rate limits** on the paid endpoints (table in [Configuration](#configuration)). Requests are
  counted only if every applicable bucket allows them; rejected attempts also count.
- **Input caps**: question length, upload size, allowed file types, history trimmed to the last 6 turns.
- **CORS** restricted to configured origins. There is **no authentication**: anyone who can reach the API can upload or
  delete documents, limited only by the per-IP upload and delete rate limits. Do not expose an instance holding private
  documents without putting authentication in front of it (reverse proxy, VPN or an auth layer).
- **Secrets**: `.env` is git-ignored and excluded from Docker images; the git history was scanned for keys before pushing.

Limits of the design: counters are in-memory and per process (a restart resets them, and several instances each count
separately, so a shared store such as Redis is needed for multi-instance deployments). Behind a reverse proxy without
`TRUST_PROXY=true`, all users share the proxy's IP and hit the limit together. These limits cap *requests*, not *spend*:
also set a monthly budget cap in the OpenAI dashboard.

## Evaluation

`python -m eval.run_eval --k 3` (or `python run.py --eval`) runs the harness. Corpus and questions are produced by
`python -m eval.build_corpus`: 20 **fictional** documents (so answers cannot come from model memory; paired domains such as
two airlines or two water boards act as distractors) and 72 golden questions, 19 of them multi-hop across two documents.
Each question stores a verbatim evidence quote; a retrieved chunk counts as a hit if it contains that quote, so scoring does
not depend on chunk IDs. Answers are judged by an LLM for correctness against the gold answer and for unsupported claims.

Metrics: **Recall@K** (share of needed evidence quotes retrieved), **Full-hit@K** (all needed evidence retrieved),
**Precision@K**, **MRR**, **answer accuracy**, **unsupported-claim rate**, and **latency p50/p95** (retrieval, first token,
end to end). Full output: [`eval/results/results.md`](eval/results/results.md) and `results.json`.

### Results on the synthetic corpus (K = 5, 72 questions, mean ± sd over 3 runs)

`python -m eval.run_eval --runs 3` repeats every LLM-dependent stage and reports mean ± sample standard deviation.
Lexical, dense and hybrid are deterministic for a fixed index, so they run once (no sd).

| Stage | Recall@5 | Full-hit@5 | MRR | Retrieval p50 / p95 (ms) |
|---|---|---|---|---|
| lexical (Postgres FTS) | 0.91 | 0.85 | 0.79 | 206 / 309 |
| dense (pgvector) | 0.87 | 0.82 | 0.74 | 877 / 1311 |
| hybrid (RRF) | 0.88 | 0.81 | 0.82 | 464 / 681 |
| hybrid + rerank (`gpt-4.1-mini`) | 0.94 ± 0.01 | 0.89 ± 0.01 | 0.87 ± 0.00 | 1483 / 1939 |
| full pipeline, no agent | 0.94 | 0.89 | 0.87 ± 0.00 | 1559 / 2004 |
| full pipeline + agent loop* | 0.94 ± 0.00 | 0.91 ± 0.01 | 0.86 ± 0.01 | 1527 / 7619 |

| Generation | Answer accuracy | Unsupported-claim rate | First token p50 / p95 (ms) | End-to-end p50 / p95 (ms) |
|---|---|---|---|---|
| no agent | 0.87 ± 0.02 | 0.006 ± 0.003 | 2471 / 3336 | 2817 / 4116 |
| with agent loop | 0.89 ± 0.01 | 0.014 ± 0.002 | 2554 / 8902 | 2798 / 9902 |

**Multi-hop questions only (Full-hit@5):** hybrid 0.32, hybrid + rerank 0.58 ± 0.05, agent loop **0.65 ± 0.03**.

What holds up once run-to-run spread is counted: reranking is a real gain over hybrid (0.81 to 0.89 full-hit), and the agent
loop's gain on multi-hop questions is real but modest on this corpus. What does **not** hold up: the agent loop's overall
answer-accuracy lift (0.87 vs 0.89 is about one sd apart) and the earlier claim that it lowers unsupported claims (it
raises them, 0.6% to 1.4%). Retrieval-only stages other than rerank have no sd because they are deterministic, so the
lexical/dense/hybrid ordering is exact for this index but reflects only these 72 questions.

### Results on a real corpus (11 IETF RFCs, 20 hand-labelled questions, K = 5, 5 runs)

`python -m eval.real_corpus --ingest`, then `python -m eval.run_eval --golden real_golden_set.json --runs 5 --out results_real_rfc`
(remove the RFCs afterwards with `python -m eval.real_corpus --remove`). The corpus is RFC 793, 1035, 3986, 5321, 6265, 6455,
6749, 7233, 7519, 8446 and 9000 (about 2,600 chunks, cleaned of page furniture, indexed alongside the synthetic documents as
distractors). The 20 questions (15 single-passage, 5 two-part) are in `eval/real_golden_set.json`, built and verified by
`eval/build_real_golden.py`: each has a verbatim evidence sentence from the RFC text, and questions are phrased differently
from the source. Full output: [`eval/results/results_real_rfc.md`](eval/results/results_real_rfc.md).

| Stage | Recall@5 | Full-hit@5 | MRR |
|---|---|---|---|
| lexical (Postgres FTS) | 0.38 | 0.30 | 0.26 |
| dense (pgvector) | 0.53 | 0.45 | 0.53 |
| hybrid (RRF) | 0.50 | 0.40 | 0.42 |
| hybrid + rerank | 0.57 ± 0.01 | 0.45 | 0.64 ± 0.01 |
| full pipeline + agent loop | 0.65 ± 0.01 | 0.59 ± 0.02 | 0.62 ± 0.02 |

Answer accuracy: 0.80 ± 0.05 without the agent, 0.88 ± 0.03 with it. Multi-part questions (5) full-hit: 0.00 for every
non-agent stage, 0.56 ± 0.09 with the agent loop.

The synthetic numbers do **not** transfer: full-hit falls from 0.89 to 0.45 for hybrid + rerank, and lexical search, the
strongest single retriever on synthetic text, is the weakest here (0.30) because RFC prose repeats the same terms across
hundreds of chunks. The agent loop's multi-part advantage does hold up, and is larger here. Failures were inspected: no
quote straddles a chunk boundary, so the misses are retrieval misses. Typically the right RFC and neighbouring chunks come
back but not the exact chunk holding a short definition (for example the JWT `iss` claim or the TLS 2^14 record limit).
Scoring counts a chunk as a hit only if it contains the labelled quote, so a different passage that also answers the
question (the TCP MSL question returned "lifetime is two minutes") counts as a miss; treat retrieval numbers as a lower bound.

### Model and reranker comparisons

Reranker (full-hit@3, sequential; `python -m eval.bench_rerank <model> ...`):

| Reranker | Full-hit@3 | MRR | Latency p50 |
|---|---|---|---|
| none (hybrid RRF) | 0.78 | 0.81 | ~0.4 s |
| local MiniLM-L6 cross-encoder (10 candidates) | 0.79 | 0.85 | 0.58 s |
| local BGE-reranker-base (10 candidates) | 0.81 | 0.82 | 2.0 s |
| LLM `gpt-4.1-nano` | 0.78 | 0.81 | ~1.8 s† |
| **LLM `gpt-4.1-mini` (default)** | 0.85 | 0.89 | ~1.5 s† |
| LLM `gpt-6-luna` | 0.86 | 0.88 | ~2.2 s† |

†measured with 4 concurrent queries, so somewhat inflated. The local rerankers are fast but barely beat no reranking on this
data; only the LLM reranker gives a real lift, costing roughly 0.9 s.

Answer model (with agent): `gpt-6-luna` accuracy 0.92 / unsupported claims 1.4%; `gpt-4.1-mini` accuracy 0.96 / unsupported
3.2% and only ~0.2 s faster to first token (retrieval dominates). `gpt-6-luna` stays the default because groundedness
matters most in RAG. Earlier runs on `gpt-4o-mini` and all-`gpt-6-luna` are kept in `eval/results/` for reference; on
`gpt-4o-mini` reranking gave no lift, which is why model choice per stage matters.

### Honest caveats

- **Latency targets are not met.** Goal was retrieval + rerank under 400 ms, first token under 1.5 s, short answer under
  4 s. Measured: retrieval + rerank ~1.3 s, first token ~2.3 s, short answer ~2.5 s p50, and multi-part questions with the
  agent reach p95 of ~8-10 s. Contributors: a remote serverless database, the LLM rerank call (~0.9 s), and the eval running
  4 queries concurrently (which inflates its numbers).
- *Agent rows retrieve up to 8 chunks (merged sub-queries) and are scored over all of them, so they are not strictly
  K=3-comparable to the retrieval-only rows.
- **The synthetic data is synthetic**: corpus and questions are LLM-generated, and the judge is the same model family as the
  generator. The real-corpus run shows the absolute numbers do not transfer (see above); use the synthetic set for relative
  comparisons only.
- **The real-corpus set is small and labelled by an LLM**: 20 questions, written by Claude from verbatim RFC sentences, not by
  an independent human, and the answer judge is still the same model family. Lean on the judge-free retrieval metrics.
  With n = 20, one question is 5 points of full-hit, so the sd across runs understates the sampling uncertainty.
- **Noise**: LLM-dependent stages are repeated (3 runs synthetic, 5 real). The remaining older tables below (reranker and
  answer-model comparisons) are single runs from before this change; their gaps of a few points are within noise.

## Tests

```bash
python -m pytest -q        # or: python run.py --test
```

None of the tests call OpenAI. Agent loop (`tests/test_agent_loop.py`, LLM and search stubbed): plan, parallel search,
reflect and the single follow-up, dedupe (first hit wins), the 8-chunk cap (best by rerank score, else fused score), plan
limits and fallbacks, history handling and the multi-part heuristic. Eval aggregation (mean, sd, noise flag). Rate limiter (per-minute, daily, upload, delete, per-IP isolation, `X-Forwarded-For`
handling, disabled and zero-disabled limits, `Retry-After`), input caps (question length, upload size, file type),
CORS allow/deny (including on 429 responses), and unit tests for chunking, RRF fusion, lexical term
handling and the scorer. There are **no** tests for the LLM calls themselves or the frontend.

## Status: done and pending

### Done
- **Backend**: schema with vector + full-text indexes; ingestion; lexical, dense, RRF and reranking (LLM and local); agent
  loop with trace events; grounded streaming generation; FastAPI SSE API with health, documents CRUD and chat.
- **Protection**: configurable per-IP rate limits, size caps, CORS allow-list.
- **Frontend**: full chat UI (streaming, markdown, citations, source cards/drawer, reasoning trace, history, upload/delete,
  themes, mobile layout, error and rate-limit states). Checked in the browser: desktop, light theme, mobile layout without
  horizontal overflow, history persistence across reload, rate-limit error state.
- **Evaluation**: corpus generator, 72-question golden set, scorer, one-command runner, reranker benchmark script, saved results.
- **Tooling**: `run.py`/`run.bat` launcher (verified start, health wait, clean stop, missing-key and busy-port errors),
  19 automated tests, Dockerfiles + compose file (validated syntactically only), planning docs.
- **Repo**: pushed to GitHub with one commit per module.

### Pending
**Targets and quality**
- Latency goals above are still missed. Ideas: stronger local reranker on a GPU, database co-located with the API, streaming
  the first tokens before reranking finishes, a faster answer model, tuning the number of rerank candidates.
- Evaluate on a **real** document corpus and with several runs to get error bars; the current numbers come from synthetic data.

**Verification gaps**
- Docker images have never been built or run (the Docker engine would not start here); treat Docker as untested.
- `run.py` was only run on Windows, and `--reset`, `--prod`, `--seed` on an empty DB and a clean-machine first run were not tested.
- No tests for the LLM wrapper or the frontend.

**Product and operations**
- **Deployment and a public demo link**: not done; needs hosting accounts (for example Fly.io or Render for the API, Vercel for `web/`).
- **Authentication**: none: uploads/deletes are open to anyone (protected only by per-IP rate limits); no user accounts, per-user documents or multi-tenancy.
- **Server-side chat storage**: history lives only in the browser.
- **Shared rate-limit store** (Redis) for multi-instance deployments.
- Ingestion is synchronous per upload (large PDFs block the request) and there is no re-ingest / dedupe of identical files.
- No observability (structured logs, metrics, cost tracking per request).
- Comparison questions can still cost several LLM calls; there is no per-request spend cap beyond the request rate limits.

## Deviations from the original plan

The original [build plan](Multi-Agent%20RAG%20Chat%20Platform%20%E2%80%94%20Build%20Plan.md) is kept in the repo. What changed:

| Plan | Built | Why |
|---|---|---|
| Claude API as the LLM | OpenAI (`gpt-6-luna`, `gpt-4.1-mini`) | an OpenAI key and models were what was available |
| Open-source BGE cross-encoder reranker | LLM listwise reranker by default; local ONNX cross-encoders (MiniLM, BGE-base) supported and benchmarked | local models gave almost no lift on this data; the LLM reranker did |
| assistant-ui or Vercel AI SDK | custom Next.js + Tailwind chat UI over SSE | full control of the trace panel and citations |
| Golden set of 30+ questions | 72 questions, 19 multi-hop | more coverage of multi-part questions |
| Latency: first token < 1.5 s, retrieval+rerank < 400 ms | ~2.3 s and ~1.3 s | see caveats; benchmarks and options documented |
| Fly.io / Render live demo | not deployed | needs accounts; local one-command run provided instead |
