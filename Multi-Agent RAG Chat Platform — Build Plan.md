# Fathom — Build Plan

Sep 27, 2026 · @Naman Kundra

## Goal and why this project

This turns two things you already have into one polished, benchmarked, chat-interface platform: [LawVista](https://claude.ai) (a RAG legal assistant) and roughly two months of work on a context-enhancement/retrieval algorithm evaluated on LongMemEval-S and BEAM. The target is a corpus-agnostic assistant with hybrid retrieval, an agent loop, and a public evaluation harness — the exact skill set named in the pgvector/hybrid-retrieval Upwork posting, and the general chat-interface pattern that recurs across nearly every other listing you found.

## Architecture

&#91;embedded content: ingestion → hybrid retrieval → agent loop → streaming UI, with an offline eval harness\]

Documents are ingested once. Each question then runs through hybrid retrieval, reranking, and an agent loop before the answer streams back — the eval harness runs offline against the same retrieval and generation stages, not in the live request path.

## Tech stack choices

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend / chat UI | Next.js + assistant-ui, or Vercel AI SDK + shadcn/ui | Streaming, tool-call rendering, and citations out of the box — fastest path to a ChatGPT-quality interface |
| Lexical retrieval | Postgres full-text search (or Tantivy) | Runs alongside pgvector with no separate service |
| Dense retrieval | pgvector on Postgres | Named directly in the target Upwork posting; one database for both indexes |
| Fusion | Reciprocal Rank Fusion (RRF) | The 2026 default for combining lexical + dense without training a fusion model |
| Reranking | Open-source BGE reranker, or Cohere Rerank | Adds meaningful ranking quality on hard queries; the open-source option keeps cost at zero |
| Agent orchestration | Hand-rolled ReAct-style loop (or LangGraph) | Full control and a visible reasoning trace — better for a demo than a black-box framework |
| LLM | Claude API | Directly relevant to postings that already build on Claude/Anthropic (e.g. the Elite Plumbing "Jarvis" listing) |
| Evaluation harness | Python scripts + a golden Q&A set, scored for Recall@K and groundedness | The single most differentiating piece — almost never built by competing applicants |
| Deployment | Docker Compose locally; Fly.io or Render for a live demo | Cheap, fast, and gives you a public link to drop straight into a proposal |

## Repo structure

```
rag-chat-platform/
  ingest/            # upload handling, chunking, embedding
  retrieval/
    lexical.py       # Postgres full-text / BM25 search
    dense.py         # pgvector similarity search
    fuse.py          # Reciprocal Rank Fusion
    rerank.py        # cross-encoder reranker
  agent/
    loop.py          # query decomposition, multi-hop retrieval, reasoning trace
  generation/
    prompt.py        # citation-grounded answer generation
  eval/
    golden_set.json  # 30+ question/answer pairs with expected sources
    scorer.py         # Recall@K, precision@K, groundedness, latency
    run_eval.py       # one-command evaluation, writes results/ for the README
  web/                # Next.js + assistant-ui chat frontend
  docker-compose.yml
  README.md           # architecture, eval numbers, latency benchmarks, demo link
```

## Build sequence, week by week

| Week | Focus | Deliverable |
| --- | --- | --- |
| 1 | Ingestion + hybrid retrieval | Upload pipeline, chunking, BM25 + pgvector dense index, RRF fusion working end to end — a CLI script returns fused results for a query |
| 2 | Reranking + eval harness | Cross-encoder reranker added; golden Q&A set (30+ questions) built; offline scorer running — one command produces real Recall@K / groundedness numbers |
| 3 | Agent loop + generation | Query decomposition, multi-hop retrieval, citation-grounded generation — the agent visibly reasons and answers multi-part questions correctly |
| 4 | Chat UI + streaming | assistant-ui (or Vercel AI SDK) frontend, streaming tokens, inline citations, a visible reasoning-trace panel — a working demo with a public link |
| 5 (stretch) | Latency + polish | Benchmark p50/p95 latency, add caching, tighten reranker size, write the README with eval numbers and a demo clip — a portfolio-ready repo |

## Evaluation harness details

This is the piece that separates you from other applicants: a golden set of 30+ question/answer pairs (with the expected source chunk for each), scored by one command against every stage of the pipeline.

| Metric | What it measures |
| --- | --- |
| Recall@K | Whether the right chunk is retrieved at all, within the top K |
| Precision@K | How much of the top K is actually relevant |
| Context precision / recall | Whether the retrieved context genuinely supports the answer |
| Groundedness / unsupported-claim rate | Whether the generated answer is backed by retrieved evidence or hallucinated |
| Latency (p50 / p95) | First-token and end-to-end response time |

Run the eval before and after adding reranking, and again before and after the agent loop, so the README can show a quality lift at each stage rather than one final number.

## UI and latency

Use assistant-ui or Vercel AI SDK + shadcn/ui: both stream tokens by default, render tool calls and citations natively, and let you show the agent's reasoning trace instead of hiding it. Stream the first token as soon as retrieval starts returning results where possible, cache embeddings so re-queries are cheap, and keep the reranker small enough that it doesn't dominate latency.

| Stage | Target |
| --- | --- |
| First token | Under 1.5s |
| Hybrid retrieval + rerank | Under 400ms |
| Full answer, short question | Under 4s |

Benchmark these for real and put the numbers in the README — a quoted p50/p95 is a concrete claim you can make in a proposal or an interview, unlike "it's fast."

## How to use this in Upwork proposals

- Lead with a specific number, not a claim: "I built a hybrid BM25 + pgvector retrieval pipeline and measured a recall lift from reranking on a 30-question golden set" beats "experienced with RAG."
- For the pgvector/hybrid-retrieval posting specifically, answer its exact screening question (a project where you used Postgres/pgvector + hybrid retrieval + reranking, and how you measured accuracy) directly from this repo's README and eval results.
- For general "AI chat interface" postings, the live demo link does the talking — attach it instead of describing the UI in prose.
- Keep the repo public with a clear README: architecture diagram, eval numbers, latency benchmarks, and a one-command way to reproduce the eval run.
