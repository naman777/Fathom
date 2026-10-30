"""Request-cost accounting must exclude the offline judge, including for historical results."""
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core import config, obs
from eval import ent_eval


@pytest.mark.parametrize("stage", ["hybrid", "rerank", "noagent", "agent"])
def test_eval_records_request_usage_before_judging(monkeypatch, stage):
    monkeypatch.setattr(config, "MODEL_PRICES", {"request-model": [1, 2], "judge-model": [10, 20]})
    chunks = [{"doc_id": "a", "content": "evidence"}]

    def search(*args, **kwargs):
        obs.record_usage("request-model", 1000, 100)
        return chunks

    def agent(*args, **kwargs):
        yield {"type": "sources", "chunks": search()}

    def answer(*args, **kwargs):
        obs.record_usage("request-model", 1000, 100)
        yield "answer"

    def judge(*args, **kwargs):
        assert obs.current() is None
        obs.record_usage("judge-model", 1000000, 1000000)
        return {"score": 1}

    monkeypatch.setattr(ent_eval.ent_search, "search", search)
    monkeypatch.setattr(ent_eval.loop, "run", agent)
    monkeypatch.setattr(ent_eval.prompt, "answer_stream", answer)
    monkeypatch.setattr(ent_eval.ent_scorer, "judge", judge)
    row = ent_eval.run_question({"question_id": "q1", "question_type": "basic", "question": "q",
                                 "expected_doc_ids": ["a"]}, stage, 5, "test", None)
    assert row["cost_usd"] == pytest.approx(0.0024 if stage in ("noagent", "agent") else 0.0012)
    assert set(row["usage"]) == {"request-model"}
    assert row["unpriced_models"] == []


def test_results_api_derives_request_cost_from_legacy_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    folder = tmp_path / "eval" / "results"
    folder.mkdir(parents=True)
    saved = {"agent": {"summary": {"n": 2}, "cost_usd": 0.02, "rows": [{"cost_usd": 0.001}, {"cost_usd": 0.003}]}}
    path = folder / "ent_results_full.json"
    path.write_text(json.dumps(saved))
    before = path.read_bytes()
    result = TestClient(app).get("/api/eval-results").json()["enterprise"]["stages"]["agent"]
    assert result["summary"]["request_cost_usd"]["mean"] == 0.002
    assert result["cost_usd"] == 0.02  # still the evaluation total including judges
    assert "rows" not in result and path.read_bytes() == before
