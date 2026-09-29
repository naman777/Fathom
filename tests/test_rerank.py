"""LLM reranker with the model stubbed."""
from retrieval import rerank


def cands(n):
    return [{"id": i, "content": f"passage {i}"} for i in range(n)]


def test_token_budget_scales_with_candidate_count(monkeypatch):
    """A fixed small budget truncated the JSON score list for large pools; the parse failure silently fell back to
    the fused order, so a wider pool looked strictly worse."""
    seen = {}

    def fake(messages, **kw):
        seen["max_tokens"] = kw["max_tokens"]
        return {"s": [0] * 30}

    monkeypatch.setattr(rerank.llm, "chat_json", fake)
    monkeypatch.setattr(rerank, "MAX_CANDIDATES", 30)
    rerank.rerank("q", cands(30), top=5)
    assert seen["max_tokens"] >= 30 * 3 + 10          # ~3 tokens per "d, " entry plus the wrapper


def test_orders_by_score_stable_and_honours_top(monkeypatch):
    monkeypatch.setattr(rerank.llm, "chat_json", lambda m, **kw: {"s": [1, 9, 9, 0]})
    out = rerank.rerank("q", cands(4), top=3)
    assert [c["id"] for c in out] == [1, 2, 0]
    assert out[0]["rerank_score"] == 9.0


def test_bad_reply_falls_back_to_fused_order(monkeypatch):
    monkeypatch.setattr(rerank.llm, "chat_json", lambda m, **kw: {})
    assert [c["id"] for c in rerank.rerank("q", cands(4), top=2)] == [0, 1]


def test_only_max_candidates_are_scored(monkeypatch):
    monkeypatch.setattr(rerank, "MAX_CANDIDATES", 3)
    monkeypatch.setattr(rerank.llm, "chat_json", lambda m, **kw: {"s": [0, 0, 5]})
    assert [c["id"] for c in rerank.rerank("q", cands(10), top=1)] == [2]
