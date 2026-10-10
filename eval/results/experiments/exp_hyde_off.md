# Evaluation results (72 questions, K=5, up to 3 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| dense (pgvector) | 1 | 0.87 | 0.82 | 0.22 | 0.74 | 923 | 1879 |  |
| hybrid (RRF) | 1 | 0.89 | 0.82 | 0.23 | 0.83 | 822 | 1797 | n/a (no sd from 1 run) |
| hybrid + rerank | 3 | 0.95 ± 0.01 | 0.94 ± 0.03 | 0.25 ± 0.01 | 0.90 ± 0.02 | 3201 | 5716 | n/a (no sd from 1 run) |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| dense (pgvector) | 0.55 | 0.37 |
| hybrid (RRF) | 0.58 | 0.32 |
| hybrid + rerank | 0.82 ± 0.05 | 0.75 ± 0.11 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| dense (pgvector) | text-embedding-3-small | 1,199 | 0 | 72 |
| hybrid + rerank | gpt-6-luna | 755,346 | 22,904 | 216 |
