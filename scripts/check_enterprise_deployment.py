"""Bounded full-agent smoke/load check for a staged collection, using the deployed API's Python environment.

    QDRANT_URL=http://qdrant25:6333 ENT_COLLECTION=enterprise_demo_25 \
      python scripts/check_enterprise_deployment.py /tmp/demo25_questions.json --out /tmp/demo25_check.json

Question file: [{question_id, question, question_type}]. Makes answer calls, no judge calls.
Does not publish benchmark-quality scores. Role checks use retrieval only, not paid answer calls.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from agent import loop
from core import config, obs
from enterprise import acl, embed, search, store
from eval.ent_scorer import latency
from generation import prompt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("questions", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()
    questions = json.loads(args.questions.read_text())
    if not questions or len(questions) > 20 or not 1 <= args.concurrency <= 4:
        ap.error("Use 1-20 questions with concurrency 1-4")
    search.search("warm up", "admin", rerank=False)
    embed._query_cached.cache_clear()

    def one(q):
        trace = obs.Trace()
        start = time.perf_counter()
        with obs.activate(trace):
            events = list(loop.run(None, q["question"], searcher=lambda text, k: search.search(text, "admin", k=k),
                                   expander=lambda cs: search.expand(cs, "admin", config.NEIGHBOR_EXPAND)))
            chunks = next(e["chunks"] for e in events if e["type"] == "sources")
            retrieval_ms = (time.perf_counter() - start) * 1000
            answer = "".join(prompt.answer_stream(q["question"], chunks))
        if not answer.strip():
            raise RuntimeError(f"Empty answer for {q['question_id']}")
        return {"question_id": q["question_id"], "question_type": q["question_type"], "retrieval_ms": retrieval_ms,
                "e2e_ms": (time.perf_counter() - start) * 1000, "answer_chars": len(answer),
                "sources": len(chunks), "sub_queries": len(events[0]["sub_questions"]),
                "followups": sum(e["type"] == "reflect" and not e["sufficient"] for e in events),
                "cost_usd": trace.summary()["cost_usd"], "unpriced_models": trace.summary()["unpriced_models"]}

    started = time.perf_counter()
    with ThreadPoolExecutor(args.concurrency) as pool:
        rows = list(pool.map(one, questions))
    # Verify every restricted role on the exact deployed search + expansion path.
    checks, leaks = 0, 0
    for role, (_, groups) in acl.ROLES.items():
        if groups is None:
            continue
        for q in questions:
            chunks = search.expand(search.search(q["question"], role, k=20, candidates=20, rerank=False),
                                   role, config.NEIGHBOR_EXPAND)
            checks += len(chunks)
            leaks += sum(not acl.can_read(role, acl.groups_for(c["source"], c["title"])) for c in chunks)
    result = {"measured_at": datetime.now(timezone.utc).isoformat(), "collection": config.ENT_COLLECTION,
              "points": store.client().get_collection(config.ENT_COLLECTION).points_count,
              "concurrency": args.concurrency, "questions": len(rows), "wall_s": time.perf_counter() - started,
              "retrieval_ms": latency([r["retrieval_ms"] for r in rows]),
              "e2e_ms": latency([r["e2e_ms"] for r in rows]),
              "api_cost_usd": sum(r["cost_usd"] for r in rows),
              "role_chunks_checked": checks, "role_chunks_leaked": leaks, "rows": rows}
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    if leaks:
        raise RuntimeError("Role leak detected")


if __name__ == "__main__":
    main()
