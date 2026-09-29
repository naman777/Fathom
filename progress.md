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

## In progress
- Nothing.

## Future
- Local BGE cross-encoder reranker; latency reduction (target first token < 1.5 s).
- Docker Compose verification; deployment (Fly.io/Render).
- Auth, persistence of chats, restrict CORS.
- Harder/real-world corpus for evaluation; rerun eval with multiple seeds.

## Notes / decisions
- OpenAI used instead of Claude (only key provided). Switched from gpt-4o-mini to `gpt-6-luna` (reasoning_effort=low); eval re-run, README updated.
- Aiven DB unreachable; user supplied a fresh Neon URL, reset once.
- Secrets are only in `.env` (git-ignored).
