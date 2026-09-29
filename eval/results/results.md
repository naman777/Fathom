# Evaluation results (72 questions, K=5, up to 3 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 1 | 0.91 | 0.85 | 0.23 | 0.79 | 206 | 309 |  |
| dense (pgvector) | 1 | 0.87 | 0.82 | 0.22 | 0.74 | 877 | 1311 | n/a (no sd from 1 run) |
| hybrid (RRF) | 1 | 0.88 | 0.81 | 0.22 | 0.82 | 464 | 681 | n/a (no sd from 1 run) |
| hybrid + rerank | 3 | 0.94 ± 0.01 | 0.89 ± 0.01 | 0.25 ± 0.00 | 0.87 ± 0.00 | 1483 | 1939 | n/a (no sd from 1 run) |
| full pipeline, no agent | 3 | 0.94 | 0.89 | 0.25 ± 0.00 | 0.87 ± 0.00 | 1559 | 2004 | within noise |
| full pipeline + agent loop | 3 | 0.94 ± 0.00 | 0.91 ± 0.01 | 0.23 ± 0.00 | 0.86 ± 0.01 | 1527 | 7619 | up |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.87 ± 0.02 | 0.006 ± 0.003 | 2471 / 3336 | 2817 / 4116 |
| full pipeline + agent loop | 0.89 ± 0.01 | 0.014 ± 0.002 | 2554 / 8902 | 2798 / 9902 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.66 | 0.42 |
| dense (pgvector) | 0.55 | 0.37 |
| hybrid (RRF) | 0.58 | 0.32 |
| hybrid + rerank | 0.76 ± 0.03 | 0.58 ± 0.05 |
| full pipeline, no agent | 0.76 | 0.58 |
| full pipeline + agent loop | 0.77 ± 0.02 | 0.65 ± 0.03 |
