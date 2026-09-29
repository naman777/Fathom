# Fathom — Implementation Plan

Decisions (made autonomously, owner unavailable):
- LLM + embeddings: OpenAI (key supplied; plan said Claude). `gpt-4o-mini` for generation/agent/rerank/judge, `text-embedding-3-small` (1536d) for dense.
- Backend: Python 3.12, FastAPI, psycopg3, Postgres (Aiven) + pgvector + built-in FTS (`tsvector`, `ts_rank_cd`).
- Reranker: LLM-based listwise reranker (no GPU/model download); interface allows swapping in BGE later.
- Frontend: Next.js (App Router) + Tailwind, custom streaming chat UI with citations and reasoning-trace panel (SSE).
- Secrets live only in `.env` (git-ignored); never written to docs.

## Phases
1. **Foundation** — repo layout, venv, config, DB reset + schema (documents, chunks, vector + FTS indexes).
2. **Ingestion** — upload (txt/md/pdf), chunking, batched embeddings, CLI + API.
3. **Hybrid retrieval** — lexical, dense, RRF fusion; CLI `python -m retrieval.search "q"`.
4. **Reranking + eval harness** — reranker; sample corpus; 30+ golden Q&A; scorer (Recall@K, Precision@K, groundedness, latency); `run_eval.py`.
5. **Agent loop + generation** — decomposition, multi-hop ReAct loop with trace, citation-grounded answers.
6. **API + streaming** — FastAPI SSE endpoints (chat, documents).
7. **Chat UI** — Next.js, streaming, inline citations, trace panel, upload.
8. **Polish** — Docker Compose, latency benchmarks, caching, README with real eval numbers.

Status tracking: see `progress.md`.
