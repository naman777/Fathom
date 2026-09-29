# Progress

## Done
- Phase 1 Foundation: venv, config, Neon Postgres + pgvector reset (`python -m core.db --reset`) and schema.
- Phase 2 Ingestion: chunking, batched embeddings, CLI + upload API (txt/md/pdf).
- Phase 3 Hybrid retrieval: FTS + pgvector HNSW + RRF.
- Phase 4 Rerank + eval: LLM listwise reranker; 20-doc fictional corpus, 72 golden Qs (19 multi-hop);
  scorer + `python -m eval.run_eval`; results in `eval/results/`.
- Phase 5 Agent loop (plan → parallel search → reflect → follow-up) + citation-grounded generation.
- Phase 6 FastAPI SSE streaming API.
- Phase 7 Next.js chat UI (streaming, citations modal, trace panel, upload/delete docs, agent/rerank toggles) — verified in browser.
- Phase 8 README with real eval numbers and caveats; Dockerfiles + docker-compose (written, untested).

- UI redesign: design tokens with light/dark theme, sidebar knowledge base with drag-drop upload, markdown answers, citation chips, source cards + drawer, live reasoning-trace panel, stop button, friendly 429 errors.
- Per-IP rate limiter (configurable in .env) plus question/upload size caps.

## Done in the follow-up round
- Latency: per-task models (reranker/planner on gpt-4.1-mini), benchmarked LLM vs local ONNX rerankers, optional local reranker (`RERANKER=local`). p95 with agent 13-15 s -> ~8 s; hybrid + rerank 2.3 s -> 1.3 s.
- Agent: tightened reflection prompt (single-entity follow-up queries); re-verified comparison questions are split correctly.
- Security: CORS origins configurable, optional ADMIN_TOKEN for upload/delete (UI prompts), delete rate limit.
- Tests: 19 pytest tests (limiter incl. daily/upload/delete caps, question/upload size caps, admin auth, CORS, chunking, RRF, scorer).
- UI: saved chat history (localStorage) with History tab; admin-token dialog; checked mobile layout (no overflow) and history persistence in browser.
- Docker: compose file validated; added .dockerignore files (keep .env and node_modules out of images).

- Launcher: `run.py` / `run.bat` (setup, health checks, clean shutdown, flags --seed/--prod/--test/--eval/--reset); verified on Windows.
- README rewritten in full (how it works, config, API, security, evaluation, status, deviations from plan).

## In progress
- Nothing.

## Pending / not possible from this machine
- Docker build/run verification (engine won't start here).
- Deploying a public demo (needs hosting accounts/credentials).
- First-token < 1.5 s and retrieval+rerank < 400 ms targets are still not met (see README).
- Real-world corpus evaluation; multi-user auth; server-side chat storage; Redis-backed rate limits.
- Admin-token dialog verified only by backend tests, not exercised in the browser.
- run.py: --reset, --prod, --seed on empty DB, clean-machine first run and Linux/macOS untested.
- No tests for the agent loop, LLM wrapper or frontend; no observability; ingestion is synchronous.

## Notes / decisions
- OpenAI used instead of Claude (only key provided). Answers, rerank and plan on gpt-6-luna (reasoning_effort=low); rerank/plan were gpt-4.1-mini until the switch (set RERANK_MODEL/PLANNER_MODEL to go back).
- Aiven DB unreachable; user supplied a fresh Neon URL, reset once.
- Secrets are only in `.env` (git-ignored).
