# Evaluation results (20 questions, K=5, up to 5 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 1 | 0.42 | 0.35 | 0.12 | 0.24 | 200 | 229 |  |
| dense (pgvector) | 1 | 0.53 | 0.45 | 0.16 | 0.53 | 987 | 1850 | n/a (no sd from 1 run) |
| hybrid (RRF) | 1 | 0.50 | 0.40 | 0.15 | 0.47 | 612 | 696 | n/a (no sd from 1 run) |
| hybrid + rerank | 5 | 0.72 ± 0.04 | 0.65 ± 0.04 | 0.22 ± 0.01 | 0.74 ± 0.05 | 1877 | 2235 | n/a (no sd from 1 run) |
| full pipeline, no agent | 5 | 0.76 ± 0.03 | 0.68 ± 0.03 | 0.23 ± 0.01 | 0.76 ± 0.04 | 1921 | 2152 | within noise |
| full pipeline + agent loop | 5 | 0.81 ± 0.01 | 0.78 ± 0.03 | 0.21 ± 0.00 | 0.74 ± 0.00 | 2224 | 6810 | up |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.86 ± 0.04 | 0.009 ± 0.012 | 3135 / 4486 | 3595 / 4978 |
| full pipeline + agent loop | 0.90 ± 0.05 | 0.005 ± 0.011 | 3353 / 7993 | 3702 / 8505 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.30 | 0.00 |
| dense (pgvector) | 0.50 | 0.20 |
| hybrid (RRF) | 0.40 | 0.00 |
| hybrid + rerank | 0.66 ± 0.09 | 0.36 ± 0.09 |
| full pipeline, no agent | 0.66 ± 0.09 | 0.36 ± 0.09 |
| full pipeline + agent loop | 0.86 ± 0.05 | 0.72 ± 0.11 |
