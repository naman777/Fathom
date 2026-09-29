# Evaluation results (72 questions, K=3)

| Stage | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms |
|---|---|---|---|---|---|---|
| lexical (BM25-style FTS) | 0.83 | 0.75 | 0.34 | 0.77 | 168 | 198 |
| dense (pgvector) | 0.78 | 0.71 | 0.31 | 0.74 | 770 | 1116 |
| hybrid (RRF) | 0.85 | 0.78 | 0.34 | 0.81 | 437 | 671 |
| hybrid + rerank | 0.91 | 0.86 | 0.38 | 0.87 | 1343 | 1670 |
| full pipeline, no agent | 0.91 | 0.86 | 0.38 | 0.88 | 1389 | 1615 |
| full pipeline + agent loop | 0.94 | 0.90 | 0.36 | 0.86 | 1405 | 7744 |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.83 | 0.026 | 2274 / 3062 | 2544 / 3731 |
| full pipeline + agent loop | 0.92 | 0.014 | 2258 / 8631 | 2517 / 9496 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| lexical (BM25-style FTS) | 0.53 | 0.21 |
| dense (pgvector) | 0.39 | 0.11 |
| hybrid (RRF) | 0.47 | 0.21 |
| hybrid + rerank | 0.66 | 0.47 |
| full pipeline, no agent | 0.66 | 0.47 |
| full pipeline + agent loop | 0.76 | 0.63 |
