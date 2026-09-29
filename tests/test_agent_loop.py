"""Agent loop with the LLM and search stubbed: plan -> search -> reflect -> follow-up, dedupe and the evidence cap.
No network, DB or OpenAI calls."""
import pytest

from agent import loop


def chunk(i, score=1.0, **kw):
    return {"id": i, "title": f"Doc{i}", "position": 0, "content": f"content {i}", "score": score, **kw}


class Stub:
    """Scripted stand-ins for llm.chat_json (planner + reflector) and search, recording every call."""

    def __init__(self, monkeypatch, corpus, plans=None, reflects=None):
        self.corpus, self.plans, self.reflects = corpus, list(plans or []), list(reflects or [])
        self.searches, self.llm_calls = [], []
        monkeypatch.setattr(loop.llm, "chat_json", self.chat_json)
        monkeypatch.setattr(loop, "hybrid", lambda conn, q, k, rerank: self._search(q, k))
        monkeypatch.setattr(loop, "_search", lambda q, rerank, k: self._search(q, k))

    def _search(self, q, k):
        self.searches.append((q, k))
        return list(self.corpus.get(q, []))[:k]

    def chat_json(self, messages, **kw):
        role = "plan" if messages[0]["content"] == loop.PLAN_SYS else "reflect"
        self.llm_calls.append(role)
        return (self.plans if role == "plan" else self.reflects).pop(0)


def run(question, **kw):
    events = list(loop.run(None, question, **kw))
    return events, {e["type"]: e for e in events}, [e["type"] for e in events]


def test_simple_question_skips_planner_and_reflection(monkeypatch):
    s = Stub(monkeypatch, {"Who founded Acme?": [chunk(1), chunk(2)]})
    _, by, types = run("Who founded Acme?")
    assert s.llm_calls == []
    assert types == ["plan", "search", "results", "sources"]
    assert by["plan"]["sub_questions"] == ["Who founded Acme?"]
    assert [c["id"] for c in by["sources"]["chunks"]] == [1, 2]


def test_multipart_plans_searches_in_parallel_then_reflects_once_when_sufficient(monkeypatch):
    s = Stub(monkeypatch, {"A?": [chunk(1)], "B?": [chunk(2)]},
             plans=[{"queries": ["A?", "B?"]}], reflects=[{"sufficient": True, "missing": "", "next_query": ""}])
    events, by, types = run("Compare A and B")
    assert s.llm_calls == ["plan", "reflect"]
    assert types == ["plan", "search", "search", "results", "results", "reflect", "sources"]
    assert [e["hop"] for e in events if e["type"] == "search"] == [1, 2]
    assert sorted(q for q, _ in s.searches) == ["A?", "B?"]
    assert {c["id"] for c in by["sources"]["chunks"]} == {1, 2}


def test_insufficient_evidence_triggers_exactly_one_followup(monkeypatch):
    s = Stub(monkeypatch, {"A?": [chunk(1)], "B?": [], "B founder": [chunk(3)], "again": [chunk(4)]},
             plans=[{"queries": ["A?", "B?"]}],
             reflects=[{"sufficient": False, "missing": "B", "next_query": "B founder"},
                       {"sufficient": False, "missing": "B", "next_query": "again"}])
    events, by, types = run("Compare A and B")
    assert loop.MAX_FOLLOWUPS == 1
    assert s.llm_calls == ["plan", "reflect"]                      # a second reflect would be a bug
    assert types.count("reflect") == 1
    follow = [e for e in events if e["type"] == "search"][-1]
    assert follow["query"] == "B founder" and follow["hop"] == 3
    assert ("B founder", 3) in s.searches                           # follow-up uses k=3
    assert "again" not in [q for q, _ in s.searches]
    assert {c["id"] for c in by["sources"]["chunks"]} == {1, 3}


@pytest.mark.parametrize("reflect", [
    {"sufficient": False, "missing": "x", "next_query": ""},         # nothing to search for
    {"sufficient": False, "missing": "x", "next_query": "A?"},       # repeats an existing sub-query
    {"sufficient": True, "missing": "", "next_query": "B founder"},  # sufficient wins over a stray query
])
def test_no_followup_when_sufficient_empty_or_repeated(monkeypatch, reflect):
    Stub(monkeypatch, {"A?": [chunk(1)], "B?": [chunk(2)], "B founder": [chunk(3)]},
         plans=[{"queries": ["A?", "B?"]}], reflects=[reflect])
    _, by, types = run("Compare A and B")
    assert types.count("search") == 2
    assert {c["id"] for c in by["sources"]["chunks"]} == {1, 2}


def test_duplicate_chunks_across_queries_are_deduped_first_hit_wins(monkeypatch):
    Stub(monkeypatch, {"A?": [chunk(1, score=0.9), chunk(2)], "B?": [chunk(1, score=0.1), chunk(3)]},
         plans=[{"queries": ["A?", "B?"]}], reflects=[{"sufficient": True}])
    _, by, _ = run("Compare A and B")
    ids = [c["id"] for c in by["sources"]["chunks"]]
    assert sorted(ids) == [1, 2, 3]
    assert next(c for c in by["sources"]["chunks"] if c["id"] == 1)["score"] == 0.9


def test_results_event_reports_per_query_counts_before_dedupe(monkeypatch):
    Stub(monkeypatch, {"A?": [chunk(1), chunk(2)], "B?": [chunk(1)]},
         plans=[{"queries": ["A?", "B?"]}], reflects=[{"sufficient": True}])
    events, _, _ = run("Compare A and B")
    counts = {e["query"]: e["count"] for e in events if e["type"] == "results"}
    assert counts == {"A?": 2, "B?": 1}


def test_evidence_capped_at_8_keeping_best_by_rerank_score(monkeypatch):
    a = [chunk(i, score=0.0, rerank_score=i) for i in range(1, 6)]    # rerank scores 1..5
    b = [chunk(i, score=0.0, rerank_score=i) for i in range(6, 11)]   # 6..10
    Stub(monkeypatch, {"A?": a, "B?": b}, plans=[{"queries": ["A?", "B?"]}], reflects=[{"sufficient": True}])
    _, by, _ = run("Compare A and B", k=8)                             # per-query k = 7, so all 10 chunks come back
    ids = [c["id"] for c in by["sources"]["chunks"]]
    assert len(ids) == loop.MAX_EVIDENCE == 8
    assert ids == [10, 9, 8, 7, 6, 5, 4, 3]                            # best first, 1 and 2 dropped


def test_cap_falls_back_to_score_when_no_rerank_score(monkeypatch):
    docs = [chunk(i, score=i / 100) for i in range(1, 7)]
    Stub(monkeypatch, {"A?": docs[:3], "B?": docs[3:],
                       "F": [chunk(7, score=0.07), chunk(8, score=0.08), chunk(9, score=0.09)]},
         plans=[{"queries": ["A?", "B?"]}], reflects=[{"sufficient": False, "next_query": "F"}])
    _, by, _ = run("Compare A and B", k=5)
    ids = [c["id"] for c in by["sources"]["chunks"]]
    assert len(ids) == 8 and 1 not in ids                              # lowest score (0.01) dropped


def test_under_cap_keeps_insertion_order_untouched(monkeypatch):
    Stub(monkeypatch, {"Q": [chunk(3, score=0.1), chunk(1, score=0.9)]})
    _, by, _ = run("Q")
    assert [c["id"] for c in by["sources"]["chunks"]] == [3, 1]


def test_plan_limited_to_four_and_junk_filtered(monkeypatch):
    s = Stub(monkeypatch, {}, plans=[{"queries": ["a", " ", 5, None, "b", "c", "d", "e", "f"]}],
             reflects=[{"sufficient": True}])
    _, by, _ = run("Compare a and b")
    assert by["plan"]["sub_questions"] == ["a", "b", "c", "d"]
    assert len(s.searches) == 4


@pytest.mark.parametrize("plan", [{}, {"queries": []}, {"queries": ["", "  "]}])
def test_bad_plan_falls_back_to_original_question(monkeypatch, plan):
    s = Stub(monkeypatch, {}, plans=[plan])
    _, by, types = run("Compare a and b")
    assert by["plan"]["sub_questions"] == ["Compare a and b"]
    assert "reflect" not in types and s.llm_calls == ["plan"]         # single query -> no reflection


def test_history_forces_planner_and_is_included_in_prompt(monkeypatch):
    seen = {}
    s = Stub(monkeypatch, {"Who founded Acme?": [chunk(1)]}, plans=[{"queries": ["Who founded Acme?"]}])
    orig = s.chat_json

    def spy(m, **kw):
        seen["msg"] = m[1]["content"]
        return orig(m, **kw)

    monkeypatch.setattr(loop.llm, "chat_json", spy)
    history = [{"role": "user", "content": "Tell me about Acme"}, {"role": "assistant", "content": "Acme is..."}]
    _, by, _ = run("Who founded it?", history=history)
    assert "user: Tell me about Acme" in seen["msg"] and "Question: Who founded it?" in seen["msg"]
    assert by["plan"]["sub_questions"] == ["Who founded Acme?"]


def test_use_agent_false_never_calls_llm(monkeypatch):
    s = Stub(monkeypatch, {"Compare A and B": [chunk(1)]})
    _, by, types = run("Compare A and B", use_agent=False)
    assert s.llm_calls == [] and "reflect" not in types
    assert by["plan"]["sub_questions"] == ["Compare A and B"]


@pytest.mark.parametrize("q,expected", [("Who founded Acme?", False), ("Compare A and B", True), ("A, B", True),
                                        ("What? Why?", True), ("What year was Acme founded", False)])
def test_multipart_heuristic(q, expected):
    assert loop._looks_multipart(q) is expected
