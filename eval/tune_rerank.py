"""Sweep the number of fused candidates the LLM reranker scores.

  python -m eval.tune_rerank [--golden real_golden_set.json] [--pool 8,20,30] [--runs 3] [--k 5] [--chars 1000]

Prints Recall / Full-hit / MRR (mean +/- sd over runs) and retrieval latency for each pool size.
"""
import argparse
import json

from core import config
from eval import scorer
from eval.run_eval import pm, retrieval_stage
from retrieval import rerank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="real_golden_set.json")
    ap.add_argument("--pool", default="8,20,30")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--chars", type=int, default=rerank.PASSAGE_CHARS)
    a = ap.parse_args()
    golden = json.loads((config.ROOT / "eval" / a.golden).read_text(encoding="utf-8"))
    rerank.PASSAGE_CHARS = a.chars
    print(f"{len(golden)} questions, K={a.k}, {a.runs} runs, passage chars={a.chars}")
    print("| Pool | Recall@K | Full-hit@K | MRR | Retr. p50 / p95 ms |\n|---|---|---|---|---|")
    for pool in (int(x) for x in a.pool.split(",")):
        rerank.MAX_CANDIDATES = pool
        agg = scorer.aggregate([scorer.summarize(retrieval_stage(golden, a.k, mode="hybrid", rerank=True, candidates=max(pool, 20)))
                                for _ in range(a.runs)])
        print(f"| {pool} | {pm(agg['recall@k'])} | {pm(agg['full_hit@k'])} | {pm(agg['mrr'])} | "
              f"{agg['retrieval_ms_p50']['mean']:.0f} / {agg['retrieval_ms_p95']['mean']:.0f} |", flush=True)


if __name__ == "__main__":
    main()
