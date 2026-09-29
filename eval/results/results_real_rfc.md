# Evaluation results (20 questions, K=5, up to 5 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 1 | 0.42 | 0.35 | 0.12 | 0.24 | 232 | 326 |  |
| dense (pgvector) | 1 | 0.53 | 0.45 | 0.16 | 0.53 | 1012 | 1450 | n/a (no sd from 1 run) |
| hybrid (RRF) | 1 | 0.50 | 0.40 | 0.15 | 0.47 | 670 | 895 | n/a (no sd from 1 run) |
| hybrid + rerank | 5 | 0.71 ± 0.01 | 0.60 | 0.22 ± 0.01 | 0.77 ± 0.03 | 2785 | 4516 | n/a (no sd from 1 run) |
| full pipeline, no agent | 5 | 0.71 ± 0.01 | 0.60 | 0.22 ± 0.01 | 0.77 ± 0.03 | 2785 | 4516 | within noise |
| full pipeline + agent loop | 5 | 0.78 ± 0.03 | 0.74 ± 0.04 | 0.22 ± 0.01 | 0.71 ± 0.04 | 4155 | 14748 | up |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.82 ± 0.06 | 0.041 ± 0.017 | 3867 / 6014 | 4267 / 6367 |
| full pipeline + agent loop | 0.89 ± 0.04 | 0.005 ± 0.010 | 5335 / 16831 | 5759 / 17163 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.30 | 0.00 |
| dense (pgvector) | 0.50 | 0.20 |
| hybrid (RRF) | 0.40 | 0.00 |
| hybrid + rerank | 0.46 ± 0.05 | 0.00 |
| full pipeline, no agent | 0.46 ± 0.05 | 0.00 |
| full pipeline + agent loop | 0.86 ± 0.05 | 0.72 ± 0.11 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| dense (pgvector) | text-embedding-3-small | 332 | 0 | 20 |
| hybrid + rerank | gpt-6-luna | 363,875 | 8,366 | 100 |
| full pipeline, no agent | gpt-6-luna | 207,906 | 14,977 | 200 |
| full pipeline + agent loop | gpt-6-luna | 773,437 | 31,494 | 399 |
| full pipeline + agent loop | text-embedding-3-small | 687 | 0 | 53 |
