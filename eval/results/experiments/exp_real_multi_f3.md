# Evaluation results (5 questions, K=5, up to 3 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| full pipeline + agent loop | 3 | 0.77 ± 0.06 | 0.53 ± 0.12 | 0.22 ± 0.01 | 0.78 ± 0.04 | 39039 | 74365 |  |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline + agent loop | 1.00 | 0.000 | 39962 / 75332 | 40318 / 75637 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| full pipeline + agent loop | 0.77 ± 0.06 | 0.53 ± 0.12 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| full pipeline + agent loop | gpt-6-luna | 363,968 | 14,013 | 143 |
| full pipeline + agent loop | text-embedding-3-small | 579 | 0 | 46 |
