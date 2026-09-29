# Evaluation results (19 questions, K=5, up to 2 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| full pipeline + agent loop | 2 | 0.91 ± 0.06 | 0.82 ± 0.11 | 0.31 ± 0.01 | 0.72 ± 0.03 | 9163 | 18889 |  |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline + agent loop | 0.74 ± 0.07 | 0.015 ± 0.013 | 10430 / 20067 | 11099 / 20899 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| full pipeline + agent loop | 0.91 ± 0.06 | 0.82 ± 0.11 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| full pipeline + agent loop | gpt-6-luna | 387,153 | 30,691 | 197 |
| full pipeline + agent loop | text-embedding-3-small | 831 | 0 | 51 |
