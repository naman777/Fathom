# Evaluation results (20 questions, K=5, up to 3 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| full pipeline, no agent | 3 | 0.87 ± 0.01 | 0.78 ± 0.03 | 0.37 ± 0.02 | 0.93 ± 0.02 | 4135 | 10432 |  |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline, no agent | 0.93 ± 0.03 | 0.015 ± 0.026 | 5373 / 12482 | 5674 / 12757 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| full pipeline, no agent | 0.67 ± 0.06 | 0.33 ± 0.12 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| full pipeline, no agent | gpt-6-luna | 588,258 | 14,539 | 180 |
| full pipeline, no agent | text-embedding-3-small | 332 | 0 | 20 |
