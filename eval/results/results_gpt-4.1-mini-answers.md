# Evaluation results (72 questions, K=3)

| Stage | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms |
|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 0.83 | 0.75 | 0.34 | 0.77 | 172 | 208 |
| dense (pgvector) | 0.78 | 0.71 | 0.31 | 0.74 | 789 | 1385 |
| hybrid (RRF) | 0.85 | 0.78 | 0.34 | 0.81 | 436 | 609 |
| hybrid + rerank | 0.90 | 0.85 | 0.38 | 0.88 | 1321 | 1591 |
| full pipeline, no agent | 0.91 | 0.86 | 0.38 | 0.88 | 1350 | 1615 |
| full pipeline + agent loop | 0.94 | 0.90 | 0.36 | 0.86 | 1408 | 7572 |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.94 | 0.070 | 2048 / 2407 | 2369 / 3515 |
| full pipeline + agent loop | 0.96 | 0.032 | 2077 / 8275 | 2417 / 10041 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.53 | 0.21 |
| dense (pgvector) | 0.39 | 0.11 |
| hybrid (RRF) | 0.47 | 0.21 |
| hybrid + rerank | 0.61 | 0.42 |
| full pipeline, no agent | 0.66 | 0.47 |
| full pipeline + agent loop | 0.79 | 0.63 |
