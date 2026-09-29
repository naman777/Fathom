# Evaluation results (19 questions, K=5, up to 2 runs)

Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic stages run once). The last column compares full-hit@K with the previous row: a change no larger than the larger sd is *within noise*.

| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |
|---|---|---|---|---|---|---|---|---|
| full pipeline + agent loop | 2 | 0.87 | 0.76 ± 0.04 | 0.29 ± 0.01 | 0.76 ± 0.06 | 10323 | 29892 |  |

## Generation

| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |
|---|---|---|---|---|
| full pipeline + agent loop | 0.74 | 0.016 ± 0.005 | 11292 / 30891 | 11668 / 31950 |

## Multi-hop questions only

| Stage | Recall@K | Full-hit@K |
|---|---|---|
| full pipeline + agent loop | 0.87 | 0.76 ± 0.04 |

## Token usage (all runs of the stage; multiply by your model prices)

| Stage | Model | Prompt tokens | Completion tokens | Calls |
|---|---|---|---|---|
| full pipeline + agent loop | gpt-6-luna | 447,161 | 37,893 | 233 |
| full pipeline + agent loop | text-embedding-3-small | 937 | 0 | 60 |
