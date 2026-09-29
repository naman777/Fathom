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
    ap.add_argument("--runs", type=int, default=3, help="repeat each LLM-dependent stage N times and report mean +/- sd")
    ap.add_argument("--golden", default="golden_set.json", help="file in eval/ (e.g. real_golden_set.json)")
    ap.add_argument("--out", default="results", help="output basename in eval/results/")
    a = ap.parse_args()
    golden = json.loads((config.ROOT / "eval" / a.golden).read_text(encoding="utf-8"))
    if a.limit:
        golden = golden[: a.limit]
    # (runner, repeatable): lexical/dense/hybrid are deterministic for a fixed index, so one run is enough;
    # anything that calls an LLM (rerank, planner, reflector, answerer, judge) is repeated --runs times.
    stages = {
        "lexical (BM25-style FTS)": (lambda: retrieval_stage(golden, a.k, mode="lexical", rerank=False), False),
        "dense (pgvector)": (lambda: retrieval_stage(golden, a.k, mode="dense", rerank=False), False),
        "hybrid (RRF)": (lambda: retrieval_stage(golden, a.k, mode="hybrid", rerank=False), False),
        "hybrid + rerank": (lambda: retrieval_stage(golden, a.k, mode="hybrid", rerank=True), True),
    }
    if not a.skip_e2e:
        stages["full pipeline, no agent"] = (lambda: e2e_stage(golden, a.k, False), True)
        stages["full pipeline + agent loop"] = (lambda: e2e_stage(golden, a.k, True), True)
    results = {}
    types = sorted({g.get("type", "single") for g in golden})
    for name, (fn, repeat) in stages.items():
        n_runs = a.runs if repeat else 1
        runs = []
        for i in range(n_runs):
            print(f"running: {name} (run {i + 1}/{n_runs})", flush=True)
            runs.append(fn())
        results[name] = {
            "summary": scorer.aggregate([scorer.summarize(rows) for rows in runs]),
            "runs": [scorer.summarize(rows) for rows in runs],
            "by_type": {t: scorer.aggregate([scorer.summarize([r for r, g in zip(rows, golden) if g.get("type", "single") == t]) for rows in runs])
                        for t in types},
            "rows": runs[-1]}
        print({k: f"{v['mean']:.3f}+/-{v['sd']:.3f}" for k, v in results[name]["summary"].items()}, flush=True)
    RES.mkdir(parents=True, exist_ok=True)
    (RES / f"{a.out}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (RES / f"{a.out}.md").write_text(to_markdown(results, a.k, len(golden)), encoding="utf-8")
    print("wrote", RES / f"{a.out}.md")


def pm(m, digits=2):
    """mean ± sd, or just the mean when the metric never varied."""
    return f"{m['mean']:.{digits}f}" + (f" ± {m['sd']:.{digits}f}" if m["sd"] else "")


def noise_flag(prev, cur):
    """'within noise' when the change in mean is no bigger than the larger of the two run-to-run sds."""
    if prev["n"] < 2 or cur["n"] < 2:
        return "n/a (no sd from 1 run)"
    gap = abs(cur["mean"] - prev["mean"])
    return "within noise" if gap <= max(prev["sd"], cur["sd"]) else ("up" if cur["mean"] > prev["mean"] else "down")


def to_markdown(results, k, n):
    runs = max(len(r["runs"]) for r in results.values())
    lines = [f"# Evaluation results ({n} questions, K={k}, up to {runs} runs)", "",
             "Values are mean ± sample standard deviation over runs; no ± means the metric never varied (deterministic "
             "stages run once). The last column compares full-hit@K with the previous row: a change no larger than the "
             "larger sd is *within noise*.", "",
             "| Stage | Runs | Recall@K | Full-hit@K | Precision@K | MRR | Retr. p50 ms | Retr. p95 ms | Δ full-hit vs prev |",
             "|---|---|---|---|---|---|---|---|---|"]
    prev = None
    for name, r in results.items():
        s = r["summary"]
        delta = noise_flag(prev, s["full_hit@k"]) if prev else ""
        lines.append(f"| {name} | {len(r['runs'])} | {pm(s['recall@k'])} | {pm(s['full_hit@k'])} | {pm(s['precision@k'])} | "
                     f"{pm(s['mrr'])} | {s['retrieval_ms_p50']['mean']:.0f} | {s['retrieval_ms_p95']['mean']:.0f} | {delta} |")
        prev = s["full_hit@k"]
    gen = {n: r["summary"] for n, r in results.items() if "answer_accuracy" in r["summary"]}
    if gen:
        lines += ["", "## Generation", "",
                  "| Pipeline | Answer accuracy | Unsupported-claim rate | First token p50/p95 ms | End-to-end p50/p95 ms |",
                  "|---|---|---|---|---|"]
        for n, s in gen.items():
            lines.append(f"| {n} | {pm(s['answer_accuracy'])} | {pm(s['unsupported_claim_rate'], 3)} | "
                         f"{s['first_token_ms_p50']['mean']:.0f} / {s['first_token_ms_p95']['mean']:.0f} | "
                         f"{s['e2e_ms_p50']['mean']:.0f} / {s['e2e_ms_p95']['mean']:.0f} |")
    multi = {n: r["by_type"].get("multi") for n, r in results.items() if r["by_type"].get("multi")}
    if multi:
        lines += ["", "## Multi-hop questions only", "", "| Stage | Recall@K | Full-hit@K |", "|---|---|---|"]
        for n, s in multi.items():
            lines.append(f"| {n} | {pm(s['recall@k'])} | {pm(s['full_hit@k'])} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
