# Evaluation results (72 questions, K=5, up to 3 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| dense (pgvector) | 1 | 0.85 | 0.79 | 0.21 | 0.77 | 4485 | 9373 |  |
| hybrid (RRF) | 1 | 0.89 | 0.83 | 0.23 | 0.80 | 970 | 1911 | n/a (no sd from 1 run) |
| hybrid + rerank | 3 | 0.97 ± 0.01 | 0.94 ± 0.01 | 0.26 ± 0.00 | 0.91 ± 0.01 | 3371 | 5482 | n/a (no sd from 1 run) |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| dense (pgvector) | 0.50 | 0.26 |
| hybrid (RRF) | 0.58 | 0.37 |
| hybrid + rerank | 0.87 ± 0.03 | 0.77 ± 0.03 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| dense (pgvector) | gpt-6-luna | 6,862 | 14,449 | 72 |
| dense (pgvector) | text-embedding-3-small | 4,213 | 0 | 144 |
| hybrid + rerank | gpt-6-luna | 751,155 | 22,206 | 216 |
