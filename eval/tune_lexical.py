"""Compare lexical retrieval modes without any LLM calls.

  python -m eval.tune_lexical [--golden real_golden_set.json] [--k 5] [--modes or,or_norm,websearch,trigram]

Prints lexical-only and hybrid (RRF with dense, no rerank) Recall / Full-hit / MRR for each mode. Dense queries use
the embeddings API (a few tokens per question), everything else is Postgres. `trigram` needs the pg_trgm extension.
"""
import argparse
import json

from core import config, db
from eval import scorer
from eval.run_eval import retrieval_stage
from retrieval import lexical


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="real_golden_set.json")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--modes", default=",".join(lexical.MODES))
    a = ap.parse_args()
    golden = json.loads((config.ROOT / "eval" / a.golden).read_text(encoding="utf-8"))
    if "trigram" in a.modes:
        with db.connect() as c:
            c.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    print(f"{len(golden)} questions, K={a.k}\n| Lexical mode | lexical: recall / full-hit / MRR | hybrid (no rerank): recall / full-hit / MRR | lexical p50 ms |\n|---|---|---|---|")
    for mode in a.modes.split(","):
        config.LEXICAL_MODE = mode
        lex = scorer.summarize(retrieval_stage(golden, a.k, mode="lexical", rerank=False))
        hyb = scorer.summarize(retrieval_stage(golden, a.k, mode="hybrid", rerank=False))
        print(f"| {mode} | {lex['recall@k']:.2f} / {lex['full_hit@k']:.2f} / {lex['mrr']:.2f} | "
              f"{hyb['recall@k']:.2f} / {hyb['full_hit@k']:.2f} / {hyb['mrr']:.2f} | {lex['retrieval_ms_p50']:.0f} |", flush=True)


if __name__ == "__main__":
    main()
