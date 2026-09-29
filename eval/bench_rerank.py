"""Compare reranker models on quality (full-hit@K, MRR) and latency: python -m eval.bench_rerank MODEL [MODEL...]"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from core import config, db
from eval import scorer
from retrieval import rerank as R
from retrieval.search import hybrid

K = 3


def main(models):
    golden = json.loads((config.ROOT / "eval" / "golden_set.json").read_text(encoding="utf-8"))
    for model in models:
        if model.startswith("local:"):
            config.RERANKER, config.LOCAL_RERANK_MODEL = "local", model[6:]
            from retrieval import rerank_local
            rerank_local._model = None
            rerank_local.warmup()
        else:
            config.RERANKER, config.RERANK_MODEL = "llm", model

        def one(item):
            with db.connect() as c:
                t = time.time()
                try:
                    ch = hybrid(c, item["question"], k=K, rerank=True)
                except Exception as e:
                    return {"err": str(e)[:80]}
                return {"ms": (time.time() - t) * 1000, **scorer.retrieval_scores(item, ch, K)}
        with ThreadPoolExecutor(int(__import__("os").environ.get("BENCH_WORKERS", "4"))) as ex:
            rows = list(ex.map(one, golden))
        errs = [r for r in rows if "err" in r]
        ok = [r for r in rows if "err" not in r]
        if not ok:
            print(model, "ERR", errs[0]); continue
        s = scorer.summarize(ok)
        print(f"{model:22} full_hit={s['full_hit@k']:.2f} recall={s['recall@k']:.2f} mrr={s['mrr']:.2f} "
              f"p50={s['retrieval_ms_p50']:.0f}ms p95={s['retrieval_ms_p95']:.0f}ms errors={len(errs)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
