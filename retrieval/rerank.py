from core import llm

SYSTEM = (
    "You rerank passages for a search query. Score each passage 0-9 by how directly it helps answer the "
    "query (9 = contains the answer). Return JSON: {\"s\": [<digit per passage, in order>]} — exactly one "
    "digit per passage."
)
MAX_CANDIDATES = 8
PASSAGE_CHARS = 1000


def rerank(query: str, candidates: list[dict], top: int = 6) -> list[dict]:
    """LLM listwise reranker: one short call scores the top fused candidates 0-9."""
    cands = candidates[:MAX_CANDIDATES]
    if len(cands) <= 1:
        return cands[:top]
    listing = "\n".join(f"[{i}] {c['content'][:PASSAGE_CHARS]}" for i, c in enumerate(cands))
    res = llm.chat_json([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Query: {query}\n\nPassages:\n{listing}"}], max_tokens=60)
    raw = res.get("s", [])
    scores = {}
    for i, v in enumerate(raw if isinstance(raw, list) else []):
        try:
            scores[i] = float(v)
        except (ValueError, TypeError):
            pass
    order = sorted(range(len(cands)), key=lambda i: (-scores.get(i, -1), i))
    return [{**cands[i], "rerank_score": scores.get(i, 0.0)} for i in order[:top]]
