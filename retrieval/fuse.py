def rrf(rankings: list[list[dict]], k: int = 60, top: int = 20) -> list[dict]:
    """Reciprocal Rank Fusion over any number of ranked lists (keyed by chunk id)."""
    scores, items = {}, {}
    for ranking in rankings:
        for rank, it in enumerate(ranking, 1):
            scores[it["id"]] = scores.get(it["id"], 0.0) + 1.0 / (k + rank)
            items.setdefault(it["id"], it)
    order = sorted(scores, key=scores.get, reverse=True)[:top]
    return [{**items[i], "score": scores[i]} for i in order]
