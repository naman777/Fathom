# Evaluation results (72 questions, K=3)

| Stage | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms |
|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 0.83 | 0.75 | 0.34 | 0.77 | 188 | 213 |
| dense (pgvector) | 0.78 | 0.71 | 0.31 | 0.74 | 830 | 1101 |
| hybrid (RRF) | 0.85 | 0.78 | 0.34 | 0.81 | 515 | 642 |
| hybrid + rerank | 0.94 | 0.90 | 0.40 | 0.92 | 2286 | 3754 |
| full pipeline, no agent | 0.94 | 0.90 | 0.41 | 0.92 | 2158 | 3244 |
| full pipeline + agent loop | 0.94 | 0.89 | 0.36 | 0.88 | 2319 | 13490 |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.88 | 0.010 | 2996 / 4300 | 3221 / 5037 |
| full pipeline + agent loop | 0.88 | 0.013 | 3221 / 14523 | 3480 / 15373 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.53 | 0.21 |
| dense (pgvector) | 0.39 | 0.11 |
| hybrid (RRF) | 0.47 | 0.21 |
| hybrid + rerank | 0.79 | 0.63 |
| full pipeline, no agent | 0.79 | 0.63 |
| full pipeline + agent loop | 0.76 | 0.58 |
