# Evaluation results (5 questions, K=5, up to 3 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| full pipeline + agent loop | 3 | 0.87 ± 0.06 | 0.73 ± 0.12 | 0.25 ± 0.02 | 0.77 ± 0.03 | 17578 | 19342 |  |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline + agent loop | 1.00 | 0.000 | 18595 / 20466 | 18792 / 20900 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| full pipeline + agent loop | 0.87 ± 0.06 | 0.73 ± 0.12 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| full pipeline + agent loop | gpt-6-luna | 262,101 | 9,253 | 103 |
| full pipeline + agent loop | text-embedding-3-small | 457 | 0 | 35 |
