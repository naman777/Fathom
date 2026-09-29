# Evaluation results (72 questions, K=5, up to 3 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 1 | 0.91 | 0.85 | 0.23 | 0.79 | 197 | 276 |  |
| dense (pgvector) | 1 | 0.87 | 0.82 | 0.22 | 0.74 | 917 | 1792 | n/a (no sd from 1 run) |
| hybrid (RRF) | 1 | 0.88 | 0.81 | 0.22 | 0.82 | 565 | 691 | n/a (no sd from 1 run) |
| hybrid + rerank | 3 | 0.93 ± 0.01 | 0.89 ± 0.02 | 0.24 ± 0.00 | 0.86 ± 0.01 | 1744 | 2174 | n/a (no sd from 1 run) |
| full pipeline, no agent | 3 | 0.93 ± 0.01 | 0.90 ± 0.01 | 0.24 ± 0.00 | 0.87 ± 0.00 | 1737 | 2153 | within noise |
| full pipeline + agent loop | 3 | 0.94 ± 0.01 | 0.90 ± 0.02 | 0.23 ± 0.00 | 0.86 ± 0.01 | 1852 | 8497 | within noise |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.88 ± 0.02 | 0.008 ± 0.010 | 2669 / 3580 | 2968 / 4274 |
| full pipeline + agent loop | 0.90 ± 0.02 | 0.006 ± 0.003 | 2810 / 9671 | 3075 / 10582 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.66 | 0.42 |
| dense (pgvector) | 0.55 | 0.37 |
| hybrid (RRF) | 0.58 | 0.32 |
| hybrid + rerank | 0.72 ± 0.03 | 0.58 ± 0.09 |
| full pipeline, no agent | 0.74 ± 0.03 | 0.63 ± 0.05 |
| full pipeline + agent loop | 0.78 ± 0.03 | 0.61 ± 0.06 |
