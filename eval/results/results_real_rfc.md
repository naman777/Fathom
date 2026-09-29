# Evaluation results (20 questions, K=5, up to 5 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 1 | 0.42 | 0.35 | 0.13 | 0.27 | 348 | 438 |  |
| dense (pgvector) | 1 | 0.53 | 0.45 | 0.16 | 0.53 | 1084 | 1718 | n/a (no sd from 1 run) |
| hybrid (RRF) | 1 | 0.50 | 0.40 | 0.15 | 0.47 | 821 | 1579 | n/a (no sd from 1 run) |
| hybrid + rerank | 5 | 0.71 ± 0.04 | 0.62 ± 0.04 | 0.23 ± 0.01 | 0.77 ± 0.04 | 3327 | 6268 | n/a (no sd from 1 run) |
| full pipeline, no agent | 5 | 0.82 ± 0.04 | 0.72 ± 0.04 | 0.32 ± 0.03 | 0.86 ± 0.04 | 3327 | 6268 | up |
| full pipeline + agent loop | 5 | 0.90 ± 0.03 | 0.85 ± 0.04 | 0.33 ± 0.02 | 0.82 ± 0.03 | 4557 | 16448 | up |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.92 ± 0.04 | 0.013 ± 0.021 | 4376 / 7710 | 4643 / 8105 |
| full pipeline + agent loop | 0.99 ± 0.02 | 0.020 ± 0.021 | 5705 / 18813 | 5982 / 19027 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.30 | 0.00 |
| dense (pgvector) | 0.50 | 0.20 |
| hybrid (RRF) | 0.40 | 0.00 |
| hybrid + rerank | 0.54 ± 0.05 | 0.16 ± 0.09 |
| full pipeline, no agent | 0.58 ± 0.04 | 0.16 ± 0.09 |
| full pipeline + agent loop | 0.82 ± 0.04 | 0.64 ± 0.09 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| dense (pgvector) | text-embedding-3-small | 332 | 0 | 20 |
| hybrid + rerank | gpt-6-luna | 368,855 | 11,430 | 100 |
| full pipeline, no agent | gpt-6-luna | 488,207 | 14,195 | 200 |
| full pipeline + agent loop | gpt-6-luna | 1,084,998 | 28,398 | 396 |
| full pipeline + agent loop | text-embedding-3-small | 646 | 0 | 50 |
