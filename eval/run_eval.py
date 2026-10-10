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
from core import config, db, llm
from eval import scorer
from generation import prompt
from retrieval import expand
from retrieval.search import hybrid

RES = config.ROOT / "eval" / "results"


def retrieval_stage(golden, k, keep_chunks=False, **kw):
    def one(item):
        with db.connect() as c:
            t = time.time()
            chunks = hybrid(c, item["question"], k=k, **kw)
            ms = (time.time() - t) * 1000
        row = {"id": item["id"], "ms": ms, **scorer.retrieval_scores(item, chunks, k)}
        return {**row, "_chunks": chunks} if keep_chunks else row
    with ThreadPoolExecutor(4) as ex:
        return list(ex.map(one, golden))


def e2e_stage(golden, k, use_agent, reuse=None):
    """Full pipeline. `reuse` maps question id -> (chunks, retrieval_ms) from an identical hybrid+rerank retrieval, so the
    no-agent pipeline does not pay for the same search and rerank calls a second time."""
    def one(item):
        with db.connect() as c:
            t = time.time()
            if reuse is not None:
                chunks, ret_ms = reuse[item["id"]]
                if config.NEIGHBOR_EXPAND:                       # same evidence assembly as agent.loop.run
                    chunks = expand.expand(c, chunks, config.NEIGHBOR_EXPAND)
            else:
                chunks = []
                for ev in loop.run(c, item["question"], rerank=True, use_agent=use_agent, k=k):
                    if ev["type"] == "sources":
                        chunks = ev["chunks"]
                ret_ms = (time.time() - t) * 1000
            t = time.time() - ret_ms / 1000                  # first-token / end-to-end still include the retrieval time
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


STAGES = {  # key -> (display name, repeatable). Deterministic stages run once; anything that calls an LLM is repeated.
    "lexical": ("lexical (BM25-style FTS)", False),
    "dense": ("dense (pgvector)", False),
    "hybrid": ("hybrid (RRF)", False),
    "rerank": ("hybrid + rerank", True),
    "noagent": ("full pipeline, no agent", True),
    "agent": ("full pipeline + agent loop", True),
}


def usage_delta(before, after):
    zero = [0, 0, 0]
    return {m: [a - b for a, b in zip(v, before.get(m, zero))] for m, v in after.items()
            if any(a != b for a, b in zip(v, before.get(m, zero)))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--skip-e2e", action="store_true", help="retrieval stages only (no answer or judge calls)")
    ap.add_argument("--stages", default="", help=f"comma list of {','.join(STAGES)} (default: all)")
    ap.add_argument("--runs", type=int, default=3, help="repeat each LLM-dependent stage N times and report mean +/- sd")
    ap.add_argument("--golden", default="golden_set.json", help="file in eval/ (e.g. real_golden_set.json)")
    ap.add_argument("--out", default="results", help="output basename in eval/results/")
    ap.add_argument("--judge-model", default="", help="model for the answer judge (default: CHAT_MODEL); a small "
                    "non-reasoning model is far cheaper but changes the accuracy baseline")
    ap.add_argument("--types", default="", help="only questions of these types, e.g. multi (multi-hop) or single")
    ap.add_argument("--followups", type=int, default=None, help="max agent follow-up searches (default: config.MAX_FOLLOWUPS)")
    ap.add_argument("--expand", type=int, default=None, help="neighbour chunks per side given to the answerer (default: config.NEIGHBOR_EXPAND)")
    ap.add_argument("--lexical-mode", default="", help="or | or_norm | websearch | trigram")
    ap.add_argument("--hyde", action="store_true", help="HyDE on the dense leg (default: config.HYDE)")
    ap.add_argument("--answer-model", default="", help="model that writes eval answers (default: CHAT_MODEL)")
    a = ap.parse_args()
    if a.followups is not None:
        loop.MAX_FOLLOWUPS = a.followups
    if a.expand is not None:
        config.NEIGHBOR_EXPAND = a.expand
    if a.lexical_mode:
        config.LEXICAL_MODE = a.lexical_mode
    if a.hyde:
        config.HYDE = True
    if a.judge_model:
        config.JUDGE_MODEL = a.judge_model
    if a.answer_model:
        config.CHAT_MODEL = a.answer_model
    golden = json.loads((config.ROOT / "eval" / a.golden).read_text(encoding="utf-8"))
    if a.types:
        golden = [g for g in golden if g.get("type", "single") in a.types.split(",")]
    if a.limit:
        golden = golden[: a.limit]
    wanted = [x for x in a.stages.split(",") if x] or [k for k in STAGES if not (a.skip_e2e and k in ("noagent", "agent"))]
    unknown = [x for x in wanted if x not in STAGES]
    if unknown:
        ap.error(f"unknown stage(s) {unknown}; choose from {list(STAGES)}")
    results, rerank_runs = {}, []
    types = sorted({g.get("type", "single") for g in golden})

    def run_once(key, i):
        if key in ("lexical", "dense", "hybrid"):
            return retrieval_stage(golden, a.k, mode=key, rerank=False)
        if key == "rerank":
            rows = retrieval_stage(golden, a.k, keep_chunks=True, mode="hybrid", rerank=True)
            rerank_runs.append({r["id"]: (r["_chunks"], r["ms"]) for r in rows})
            return [{k: v for k, v in r.items() if k != "_chunks"} for r in rows]
        if key == "noagent":
            return e2e_stage(golden, a.k, False, reuse=rerank_runs[i] if i < len(rerank_runs) else None)
        return e2e_stage(golden, a.k, True)

    for key in (k for k in STAGES if k in wanted):
        name, repeat = STAGES[key]
        n_runs = a.runs if repeat else 1
        runs, before = [], llm.usage_snapshot()
        for i in range(n_runs):
            print(f"running: {name} (run {i + 1}/{n_runs})", flush=True)
            runs.append(run_once(key, i))
        results[name] = {
            "summary": scorer.aggregate([scorer.summarize(rows) for rows in runs]),
            "runs": [scorer.summarize(rows) for rows in runs],
            "by_type": {t: scorer.aggregate([scorer.summarize([r for r, g in zip(rows, golden) if g.get("type", "single") == t]) for rows in runs])
                        for t in types},
            "usage": usage_delta(before, llm.usage_snapshot()),
            "rows": runs[-1]}
        print({k: f"{v['mean']:.3f}+/-{v['sd']:.3f}" for k, v in results[name]["summary"].items()}, flush=True)
        print("  tokens [prompt, completion, calls]:", results[name]["usage"], flush=True)
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
    usage = {n: r["usage"] for n, r in results.items() if r.get("usage")}
    if usage:
        lines += ["", "## Token usage (all runs of the stage; multiply by your model prices)", "",
                  "| Stage | Model | Prompt tokens | Completion tokens | Calls |", "|---|---|---|---|---|"]
        for n, u in usage.items():
            for m, (pt, ct, calls) in sorted(u.items()):
                lines.append(f"| {n} | {m} | {pt:,} | {ct:,} | {calls:,} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
