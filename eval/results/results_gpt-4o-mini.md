# Evaluation results (72 questions, K=3)

| Stage | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms |
|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 0.83 | 0.75 | 0.34 | 0.76 | 182 | 219 |
| dense (pgvector) | 0.78 | 0.71 | 0.31 | 0.74 | 792 | 1189 |
| hybrid (RRF) | 0.85 | 0.78 | 0.34 | 0.81 | 466 | 619 |
| hybrid + rerank | 0.85 | 0.79 | 0.34 | 0.82 | 1482 | 1861 |
| full pipeline, no agent | 0.86 | 0.79 | 0.35 | 0.83 | 1519 | 1999 |
| full pipeline + agent loop | 0.90 | 0.85 | 0.33 | 0.80 | 1563 | 9385 |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.90 | 0.082 | 2223 / 2623 | 2608 / 3821 |
| full pipeline + agent loop | 0.90 | 0.050 | 2360 / 10182 | 2787 / 12863 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.53 | 0.21 |
| dense (pgvector) | 0.39 | 0.11 |
| hybrid (RRF) | 0.47 | 0.21 |
| hybrid + rerank | 0.42 | 0.21 |
| full pipeline, no agent | 0.47 | 0.21 |
| full pipeline + agent loop | 0.63 | 0.42 |
