"""Observability: cost math, stage shares, trace lifecycle, and propagation into the agent loop's worker threads."""
import time

from agent import loop
from core import obs


def test_cost_of_priced_and_unpriced_models():
    usage = {"a": [1_000_000, 500_000, 3], "b": [2_000, 100, 1], "z": [10, 10, 1]}
    usd, unpriced = obs.cost_of(usage, {"a": [0.4, 1.6], "b": [1.0, 2.0]})
    assert abs(usd - (0.4 + 0.8 + 0.002 + 0.0002)) < 1e-9
    assert unpriced == ["z"]


def test_stage_is_noop_without_trace_and_accumulates_with_one():
    with obs.stage("rerank"):
        pass  # must not raise
    t = obs.Trace(question_chars=5)
    with obs.activate(t):
        with obs.stage("rerank"):
            time.sleep(0.01)
        with obs.stage("rerank"):
            time.sleep(0.01)
        obs.record_usage("m", 100, 10)
    assert t.stages["rerank"] >= 20 and t.usage["m"] == [100, 10, 1]
    assert obs.current() is None                      # deactivated afterwards


def test_summary_shares_only_count_leaf_stages_and_sum_to_100():
    t = obs.Trace()
    for name, ms in {"rerank": 600.0, "dense": 300.0, "lexical": 100.0, "retrieval_total": 5000.0}.items():
        t.add_stage(name, ms)
    s = t.summary()
    assert s["stage_share_pct"] == {"rerank": 60.0, "dense": 30.0, "lexical": 10.0}
    assert s["top_stage"] == "rerank" and "retrieval_total" in s["stages_ms"]


def test_finish_logs_and_feeds_stats(caplog):
    obs.RECENT.clear()
    obs.log.propagate = True
    with caplog.at_level("INFO", logger="fathom.request"):
        t = obs.Trace(question_chars=12, agent=True)
        t.add_usage("gpt-4.1-mini", 1_000_000, 0)
        t.add_stage("rerank", 50)
        t.finish("ok", n_sources=3)
    assert any('"trace_id":"' + t.trace_id in r.message for r in caplog.records)
    st = obs.stats()
    assert st["requests"] == 1 and st["errors"] == 0 and abs(st["cost_usd_avg"] - 0.40) < 1e-9
    obs.log.propagate = False
    obs.RECENT.clear()


def test_stats_flags_unpriced_requests():
    obs.RECENT.clear()
    t = obs.Trace()
    t.add_usage("mystery-model", 10, 10)
    t.finish("ok")
    st = obs.stats()
    assert st["cost_usd_avg"] is None and st["requests_with_unpriced_models"] == 1
    obs.RECENT.clear()


def test_traced_reactivates_trace_on_every_step():
    t = obs.Trace()
    seen = []

    def inner():
        for _ in range(3):
            seen.append(obs.current())
            yield 1

    assert list(obs.traced(inner(), t)) == [1, 1, 1]
    assert all(x is t for x in seen) and obs.current() is None


def test_agent_worker_threads_report_to_the_active_trace(monkeypatch):
    """Regression: parallel sub-query searches run in a thread pool; their LLM usage and stage time must land on the
    request's trace (the context has to be captured in the calling thread)."""
    def fake_search(q, rerank, k):
        with obs.stage("rerank"):
            obs.record_usage("m", 10, 1)
        return [{"id": hash(q) % 1000, "title": "T", "position": 0, "content": q, "score": 1.0}]

    monkeypatch.setattr(loop, "_search", fake_search)
    monkeypatch.setattr(loop.llm, "chat_json", lambda m, **kw: {"queries": ["a", "b", "c"], "sufficient": True})
    t = obs.Trace()
    with obs.activate(t):
        list(loop.run(None, "compare a and b and c"))
    assert t.usage["m"] == [30, 3, 3]                    # three parallel searches, all counted
    assert t.stages["rerank"] > 0
