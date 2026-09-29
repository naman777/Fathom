"""One-command evaluation: python -m eval.run_eval [--limit N] [--k 5]

Stages: lexical -> dense -> hybrid(RRF) -> hybrid+rerank (retrieval only), then full generation with and
without the agent loop (answer accuracy, groundedness, first-token / end-to-end latency).
Writes eval/results/results.json and eval/results/results.md.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor

from agent import loop
from core import config, db
from eval import scorer
from generation import prompt
from retrieval.search import hybrid

RES = config.ROOT / "eval" / "results"


def retrieval_stage(golden, k, **kw):
    def one(item):
        with db.connect() as c:
            t = time.time()
            chunks = hybrid(c, item["question"], k=k, **kw)
            ms = (time.time() - t) * 1000
        return {"id": item["id"], "ms": ms, **scorer.retrieval_scores(item, chunks, k)}
    with ThreadPoolExecutor(4) as ex:
        return list(ex.map(one, golden))


def e2e_stage(golden, k, use_agent):
    def one(item):
        with db.connect() as c:
            t = time.time()
            chunks = []
            for ev in loop.run(c, item["question"], rerank=True, use_agent=use_agent, k=k):
                if ev["type"] == "sources":
                    chunks = ev["chunks"]
            ret_ms = (time.time() - t) * 1000
            first, parts = None, []
            for tok in prompt.answer_stream(item["question"], chunks):
                if first is None:
                    first = (time.time() - t) * 1000
                parts.append(tok)
            e2e = (time.time() - t) * 1000
        answer = "".join(parts)
        row = {"id": item["id"], "ms": ret_ms, "first_token_ms": first or e2e, "e2e_ms": e2e,
               **scorer.retrieval_scores(item, chunks, len(chunks) or 1), **scorer.judge(item, chunks, answer)}
        return row
    with ThreadPoolExecutor(4) as ex:
        return list(ex.map(one, golden))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--skip-e2e", action="store_true")
    a = ap.parse_args()
    golden = json.loads((config.ROOT / "eval" / "golden_set.json").read_text(encoding="utf-8"))
    if a.limit:
        golden = golden[: a.limit]
    stages = {
        "lexical (BM25-style FTS)": lambda: retrieval_stage(golden, a.k, mode="lexical", rerank=False),
        "dense (pgvector)": lambda: retrieval_stage(golden, a.k, mode="dense", rerank=False),
        "hybrid (RRF)": lambda: retrieval_stage(golden, a.k, mode="hybrid", rerank=False),
        "hybrid + rerank": lambda: retrieval_stage(golden, a.k, mode="hybrid", rerank=True),
    }
    if not a.skip_e2e:
        stages["full pipeline, no agent"] = lambda: e2e_stage(golden, a.k, False)
        stages["full pipeline + agent loop"] = lambda: e2e_stage(golden, a.k, True)
    results = {}
    for name, fn in stages.items():
        print("running:", name, flush=True)
        rows = fn()
        results[name] = {"summary": scorer.summarize(rows),
                         "by_type": {t: scorer.summarize([r for r, g in zip(rows, golden) if g["type"] == t])
                                     for t in ("single", "multi") if any(g["type"] == t for g in golden)},
                         "rows": rows}
        print({k: round(v, 3) for k, v in results[name]["summary"].items()}, flush=True)
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (RES / "results.md").write_text(to_markdown(results, a.k, len(golden)), encoding="utf-8")
    print("wrote", RES / "results.md")


def to_markdown(results, k, n):
    lines = [f"# Evaluation results ({n} questions, K={k})", "",
             "| Stage | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms |", "|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        s = r["summary"]
        lines.append(f"| {name} | {s['recall@k']:.2f} | {s['full_hit@k']:.2f} | {s['precision@k']:.2f} | "
                     f"{s['mrr']:.2f} | {s['retrieval_ms_p50']:.0f} | {s['retrieval_ms_p95']:.0f} |")
    gen = {n: r["summary"] for n, r in results.items() if "answer_accuracy" in r["summary"]}
    if gen:
        lines += ["", "## Generation", "",
                  "| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |",
                  "|---|---|---|---|---|"]
        for n, s in gen.items():
            lines.append(f"| {n} | {s['answer_accuracy']:.2f} | {s['unsupported_claim_rate']:.3f} | "
                         f"{s['first_token_ms_p50']:.0f} / {s['first_token_ms_p95']:.0f} | "
                         f"{s['e2e_ms_p50']:.0f} / {s['e2e_ms_p95']:.0f} |")
    multi = {n: r["by_type"].get("multi") for n, r in results.items() if r["by_type"].get("multi")}
    if multi:
        lines += ["", "## Multi-hop questions only", "", "| Stage | Recall@K | Full-hit@K |", "|---|---|---|"]
        for n, s in multi.items():
            lines.append(f"| {n} | {s['recall@k']:.2f} | {s['full_hit@k']:.2f} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
