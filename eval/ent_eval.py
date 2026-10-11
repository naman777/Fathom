"""Evaluate enterprise search on the EnterpriseRAG-Bench questions.

    python -m eval.ent_eval --stages lexical,dense,hybrid                 # retrieval only, no API calls
    python -m eval.ent_eval --stages rerank,noagent,agent --limit 100     # LLM stages on a stratified sample
    python -m eval.ent_eval --collection enterprise_dev --out ent_results_dev

Stages: lexical | dense | hybrid (Qdrant only), rerank (hybrid + LLM reranker), noagent (rerank + neighbour expansion +
answer + judge), agent (the full agent loop + answer + judge). Runs as the admin role so access rules do not hide gold
documents; eval/ent_leak_test.py measures the access rules separately.

Metrics are defined in eval/ent_scorer.py. Latency is measured per question at --concurrency parallel questions and
reported as p50 / p95 / p99. With 500 questions, p99 is the 5th slowest, so read it as an indication, not a guarantee.
"""
import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor

from agent import loop
from core import config, llm, obs
from enterprise import data, embed, search as ent_search
from eval import ent_scorer
from generation import prompt

RETRIEVAL_STAGES = ("lexical", "dense", "hybrid", "rerank")
ALL_STAGES = RETRIEVAL_STAGES + ("noagent", "agent")
ROLE = "admin"


def sample(questions: list[dict], limit: int, seed: int = 0) -> list[dict]:
    """Stratified by question type so a small run still covers every category."""
    if not limit or limit >= len(questions):
        return questions
    rng, out = random.Random(seed), []
    types = sorted({q["question_type"] for q in questions})
    for t in types:
        qs = [q for q in questions if q["question_type"] == t]
        out += rng.sample(qs, max(1, round(limit * len(qs) / len(questions))))
    return out


def run_question(q: dict, stage: str, k: int, collection: str, judge_model: str | None) -> dict:
    row = {"question_id": q["question_id"], "question_type": q["question_type"]}
    trace = obs.Trace()
    with obs.activate(trace):
        t = time.perf_counter()
        if stage in ("lexical", "dense", "hybrid"):
            chunks = ent_search.search(q["question"], ROLE, k=4 * k, candidates=4 * k, rerank=False, mode=stage, collection=collection)
        elif stage == "rerank":
            chunks = ent_search.search(q["question"], ROLE, k=k, rerank=True, collection=collection)
        else:
            events = loop.run(None, q["question"], rerank=True, use_agent=stage == "agent", k=k,
                              searcher=lambda s, n: ent_search.search(s, ROLE, k=n, rerank=True, collection=collection),
                              expander=lambda cs: ent_search.expand(cs, ROLE, config.NEIGHBOR_EXPAND, collection))
            chunks = next(e["chunks"] for e in events if e["type"] == "sources")
        row["retrieval_ms"] = (time.perf_counter() - t) * 1000
        row.update(ent_scorer.retrieval_scores(q, chunks, k if stage in RETRIEVAL_STAGES else len(chunks)))
        row["docs_retrieved"] = len(ent_scorer.doc_ranking(chunks)[:k] if stage in RETRIEVAL_STAGES else ent_scorer.doc_ranking(chunks))
        if stage in ("noagent", "agent"):
            answer, first = "", None
            for tok in prompt.answer_stream(q["question"], chunks):
                if first is None:
                    first = (time.perf_counter() - t) * 1000
                answer += tok
            row["first_token_ms"] = first if first is not None else (time.perf_counter() - t) * 1000
            row["e2e_ms"] = (time.perf_counter() - t) * 1000
            row["answer"] = answer
    if stage in ("noagent", "agent"):  # judged outside the trace so its tokens are not counted as request cost
        row.update(ent_scorer.judge(q, chunks, row["answer"], judge_model))
        row["stages_ms"] = trace.summary()["stages_ms"]
        row["cost_usd"] = trace.summary()["cost_usd"]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="lexical,dense,hybrid")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--collection", default=config.ENT_COLLECTION)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--out", default="ent_results")
    a = ap.parse_args()

    questions = sample(data.questions(), a.limit)
    path = config.ROOT / "eval" / "results" / f"{a.out}.json"
    results = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    ent_search.search("warm up", ROLE, rerank=False, collection=a.collection)  # load the query encoder before timing
    for stage in a.stages.split(","):
        assert stage in ALL_STAGES, stage
        embed._query_cached.cache_clear()  # every stage pays for its own query embeddings, so latencies are comparable
        before, t = llm.usage_snapshot(), time.time()
        with ThreadPoolExecutor(a.concurrency) as ex:
            rows = list(ex.map(lambda q: run_question(q, stage, a.k, a.collection, a.judge_model), questions))
        after = llm.usage_snapshot()
        usage = {m: [x - y for x, y in zip(v, before.get(m, [0, 0, 0]))] for m, v in after.items()}
        usage = {m: v for m, v in usage.items() if v[2]}
        results[stage] = {"summary": ent_scorer.summarize(rows), "by_type": ent_scorer.by_type(rows), "usage": usage,
                          "cost_usd": round(obs.cost_of(usage)[0], 4),
                          "config": {"k": a.k, "collection": a.collection, "questions": len(rows), "concurrency": a.concurrency,
                                     "embed_model": config.ENT_EMBED_MODEL, "rerank_model": config.RERANK_MODEL,
                                     "answer_model": config.CHAT_MODEL, "judge_model": a.judge_model or config.JUDGE_MODEL or config.CHAT_MODEL,
                                     "wall_s": round(time.time() - t, 1)},
                          "rows": rows}
        path.write_text(json.dumps(results, indent=1), encoding="utf-8")
        s = results[stage]["summary"]
        print(f"\n== {stage} ({len(rows)} questions, {time.time() - t:.0f}s, ${results[stage]['cost_usd']})")
        print("  " + "  ".join(f"{m}={s[m]:.3f}" for m in ("context_recall", "context_precision", "full_hit", "mrr", "overall_score",
                                                              "answer_correctness", "answer_completeness", "factuality") if m in s))
        for key in ("retrieval_ms", "first_token_ms", "e2e_ms"):
            if key in s:
                print(f"  {key}: p50={s[key]['p50']:.0f} p95={s[key]['p95']:.0f} p99={s[key]['p99']:.0f}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
