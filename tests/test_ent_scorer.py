from eval import ent_scorer as s


def _chunks(*doc_ids):
    return [{"doc_id": d, "content": d} for d in doc_ids]


def test_retrieval_scores_are_document_level():
    item = {"expected_doc_ids": ["a", "b"]}
    r = s.retrieval_scores(item, _chunks("x", "a", "a", "y"), k=3)  # docs in rank order: x, a, y
    assert r["recall"] == 0.5 and r["precision"] == 1 / 3 and r["mrr"] == 0.5 and r["full_hit"] is False


def test_retrieval_scores_full_hit_and_k_cutoff():
    item = {"expected_doc_ids": ["a", "b"]}
    assert s.retrieval_scores(item, _chunks("a", "b", "c"), k=2)["full_hit"] is True
    assert s.retrieval_scores(item, _chunks("c", "d", "a", "b"), k=2)["recall"] == 0.0


def test_questions_without_gold_documents_are_skipped():
    assert s.retrieval_scores({"expected_doc_ids": []}, _chunks("a"), k=5) == {}


def test_judge_scoring(monkeypatch):
    item = {"question": "q", "gold_answer": "g", "answer_facts": ["f1", "f2", "f3", "f4"]}
    monkeypatch.setattr(s.llm, "chat_json", lambda *a, **k: {"facts": [True, True, False], "correct": True, "claims": 4, "unsupported": 9})
    r = s.judge(item, _chunks("a"), "answer")
    assert r["completeness"] == 0.5 and r["score"] == 0.5 and r["unsupported"] == 4  # missing fact = not covered; clamped
    monkeypatch.setattr(s.llm, "chat_json", lambda *a, **k: {"facts": [True] * 4, "correct": False, "claims": 1, "unsupported": 0})
    assert s.judge(item, _chunks("a"), "answer")["score"] == 0.0  # an incorrect answer scores 0 however complete
    monkeypatch.setattr(s.llm, "chat_json", lambda *a, **k: {})
    assert s.judge(item, _chunks("a"), "answer")["judged"] is False


def test_summarize_separates_retrieval_and_generation():
    rows = [{"question_type": "basic", "recall": 1.0, "precision": 0.5, "full_hit": True, "mrr": 1.0, "retrieval_ms": 100,
             "score": 1.0, "correct": True, "completeness": 1.0, "claims": 3, "unsupported": 0, "judged": True, "e2e_ms": 900},
            {"question_type": "info_not_found", "retrieval_ms": 300, "score": 0.0, "correct": False, "completeness": 0.0,
             "claims": 1, "unsupported": 1, "judged": True, "e2e_ms": 1100}]
    out = s.summarize(rows)
    assert out["n_retrieval"] == 1 and out["n_generation"] == 2
    assert out["overall_score"] == 0.5 and out["factuality"] == 0.75
    assert out["retrieval_ms"]["p99"] == 300 and set(s.by_type(rows)) == {"basic", "info_not_found"}
