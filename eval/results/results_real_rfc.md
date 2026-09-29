# Evaluation results (20 questions, K=5, up to 5 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 1 | 0.38 | 0.30 | 0.10 | 0.26 | 218 | 257 |  |
| dense (pgvector) | 1 | 0.53 | 0.45 | 0.16 | 0.53 | 989 | 1997 | n/a (no sd from 1 run) |
| hybrid (RRF) | 1 | 0.50 | 0.40 | 0.15 | 0.42 | 635 | 729 | n/a (no sd from 1 run) |
| hybrid + rerank | 5 | 0.57 ± 0.01 | 0.45 | 0.17 ± 0.00 | 0.64 ± 0.01 | 1561 | 1786 | n/a (no sd from 1 run) |
| full pipeline, no agent | 5 | 0.57 | 0.45 | 0.17 | 0.66 ± 0.01 | 1595 | 1878 | within noise |
| full pipeline + agent loop | 5 | 0.65 ± 0.01 | 0.59 ± 0.02 | 0.18 ± 0.00 | 0.62 ± 0.02 | 1715 | 5727 | up |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.80 ± 0.05 | 0.039 ± 0.015 | 2636 / 3105 | 2980 / 3661 |
| full pipeline + agent loop | 0.88 ± 0.03 | 0.047 ± 0.019 | 3012 / 6779 | 3484 / 7183 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.30 | 0.00 |
| dense (pgvector) | 0.50 | 0.20 |
| hybrid (RRF) | 0.40 | 0.00 |
| hybrid + rerank | 0.48 ± 0.04 | 0.00 |
| full pipeline, no agent | 0.50 | 0.00 |
| full pipeline + agent loop | 0.78 ± 0.04 | 0.56 ± 0.09 |
