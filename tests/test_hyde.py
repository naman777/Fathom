"""HyDE with the model, embeddings and database stubbed. No network."""
import pytest

from core import config
from retrieval import hyde, search

VECS = {"q": [1.0, 0.0], "hypothetical passage": [0.0, 1.0]}


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    hyde._generate_cached.cache_clear()
    monkeypatch.setattr(hyde.llm, "embed_query", lambda text: VECS[text])


def test_vector_is_the_mean_of_question_and_hypothetical_passage(monkeypatch):
    monkeypatch.setattr(hyde.llm, "chat", lambda m, **kw: " hypothetical passage\n")
    assert hyde.query_vector("q") == [0.5, 0.5]


def test_passage_is_generated_once_per_query(monkeypatch):
    calls = []
    monkeypatch.setattr(hyde.llm, "chat", lambda m, **kw: calls.append(kw["model"]) or "hypothetical passage")
    hyde.query_vector("q")
    hyde.query_vector("q")
    assert calls == [config.HYDE_MODEL]


@pytest.mark.parametrize("reply", ["", RuntimeError("model down")])
def test_falls_back_to_the_question_embedding(monkeypatch, reply):
    def fake(m, **kw):
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(hyde.llm, "chat", fake)
    assert hyde.query_vector("q") == [1.0, 0.0]


@pytest.mark.parametrize("on,expected", [(True, [0.5, 0.5]), (False, None)])
def test_only_the_dense_leg_uses_the_hyde_vector(monkeypatch, on, expected):
    seen = {}
    monkeypatch.setattr(config, "HYDE", on)
    monkeypatch.setattr(hyde.llm, "chat", lambda m, **kw: "hypothetical passage")
    monkeypatch.setattr(search.lexical, "search", lambda conn, q, k, doc_ids: seen.update(lexical=q) or [{"id": 1}])
    monkeypatch.setattr(search.dense, "search",
                        lambda conn, q, k, doc_ids, vector=None: seen.update(dense=q, vector=vector) or [{"id": 2}])
    out = search.hybrid(None, "q", rerank=False)
    assert seen == {"lexical": "q", "dense": "q", "vector": expected}
    assert {c["id"] for c in out} == {1, 2}
