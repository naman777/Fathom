"""Hand-rolled ReAct-style research agent.

Yields trace events (dicts) so the UI / eval can show visible reasoning:
  {"type": "plan", "sub_questions": [...]}
  {"type": "search", "query": ..., "hop": n}
  {"type": "results", "query": ..., "count": n, "titles": [...]}
  {"type": "reflect", "sufficient": bool, "missing": str, "next_query": str}
  {"type": "sources", "chunks": [...]}          # final evidence set (numbered by the caller)

Flow: plan (decompose) -> parallel search per sub-question -> reflect (multi-part questions only) ->
optional follow-up hop (at most MAX_FOLLOWUPS) -> evidence.
"""
import re
from concurrent.futures import ThreadPoolExecutor

from core import config, db, llm
from retrieval.search import hybrid

MAX_FOLLOWUPS = 1
MAX_EVIDENCE = 8

PLAN_SYS = (
    "Decompose the user's question into the minimal set of standalone search queries needed to answer it. "
    "Simple questions need exactly one. Multi-part or comparative questions need one per part. "
    "Use conversation context to resolve pronouns. Return JSON: {\"queries\": [\"...\"]} (max 4)."
)
REFLECT_SYS = (
    "You judge whether gathered evidence is enough to fully answer the question. Be strict about entities: "
    "every entity or part named in the question must have supporting evidence. "
    "Return JSON: {\"sufficient\": true|false, \"missing\": \"what is missing\", "
    "\"next_query\": \"ONE standalone search query about a SINGLE entity/topic that is missing "
    "(never combine several entities or use ';'), or empty\"}."
)


MULTIPART = re.compile(r"\b(and|compare|comparison|versus|vs|both|between|difference|differ|also|each|all)\b|[,;]", re.I)


def _looks_multipart(q: str) -> bool:
    """Cheap heuristic so simple questions skip the planner LLM call."""
    return bool(MULTIPART.search(q)) or q.count("?") > 1


def _search(q, rerank, k):
    with db.connect() as c:
        return hybrid(c, q, k=k, rerank=rerank)


def run(conn, question: str, history=None, rerank=True, use_agent=True, k=5):
    ctx = ""
    if history:
        ctx = "Conversation so far:\n" + "\n".join(
            f"{m['role']}: {m['content'][:300]}" for m in history[-4:]) + "\n\n"

    queries = [question]
    if use_agent and (history or _looks_multipart(question)):
        plan = llm.chat_json([{"role": "system", "content": PLAN_SYS},
                              {"role": "user", "content": f"{ctx}Question: {question}"}], max_tokens=200, model=config.PLANNER_MODEL)
        queries = [q for q in plan.get("queries", []) if isinstance(q, str) and q.strip()][:4] or [question]
    yield {"type": "plan", "sub_questions": queries}

    evidence: dict[int, dict] = {}
    hop = 0

    def do_round(qs, per):
        nonlocal hop
        for q in qs:
            hop += 1
            yield {"type": "search", "query": q, "hop": hop}
        if len(qs) == 1:
            results = [hybrid(conn, qs[0], k=per, rerank=rerank)]
        else:
            with ThreadPoolExecutor(len(qs)) as ex:
                results = list(ex.map(lambda q: _search(q, rerank, per), qs))
        for q, res in zip(qs, results):
            for r in res:
                evidence.setdefault(r["id"], r)
            yield {"type": "results", "query": q, "count": len(res),
                   "titles": [f"{r['title']}#{r['position']}" for r in res]}

    yield from do_round(queries, k if len(queries) == 1 else max(3, k - 1))

    if use_agent and len(queries) > 1:
        seen = set(queries)
        for _ in range(MAX_FOLLOWUPS):
            listing = "\n".join(f"- {e['content'][:300]}" for e in evidence.values())
            ref = llm.chat_json([{"role": "system", "content": REFLECT_SYS},
                                 {"role": "user", "content": f"Question: {question}\n\nEvidence:\n{listing}"}],
                                max_tokens=150, model=config.PLANNER_MODEL)
            nq = (ref.get("next_query") or "").strip()
            suff = bool(ref.get("sufficient", True))
            yield {"type": "reflect", "sufficient": suff, "missing": ref.get("missing", ""), "next_query": nq}
            if suff or not nq or nq in seen:
                break
            seen.add(nq)
            yield from do_round([nq], 3)

    chunks = list(evidence.values())
    if len(chunks) > MAX_EVIDENCE:
        chunks = sorted(chunks, key=lambda c: -c.get("rerank_score", c["score"]))[:MAX_EVIDENCE]
    yield {"type": "sources", "chunks": chunks}
