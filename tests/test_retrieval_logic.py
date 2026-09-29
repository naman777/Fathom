from ingest.chunking import split_text
from retrieval.fuse import rrf
from retrieval.lexical import _terms
from eval.scorer import retrieval_scores


def test_chunks_respect_size_and_overlap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(12))
    chunks = split_text(text, target=500, overlap=100)
    assert len(chunks) > 3
    assert all(len(c) <= 500 + 120 for c in chunks)
    assert "Paragraph 0" in chunks[0] and "Paragraph 11" in chunks[-1]


def test_empty_text_gives_no_chunks():
    assert split_text("   \n\n  ") == []


def test_rrf_prefers_items_ranked_high_in_both_lists():
    a = [{"id": 1}, {"id": 2}, {"id": 3}]
    b = [{"id": 3}, {"id": 1}, {"id": 4}]
    out = rrf([a, b])
    assert [x["id"] for x in out][:2] == [1, 3]
    assert {x["id"] for x in out} == {1, 2, 3, 4}


def test_lexical_terms_dedupe_and_strip_punctuation():
    assert _terms("Who founded Meridian, Meridian?") == ["who", "founded", "meridian"]
    assert _terms("!!") == []


def test_scorer_recall_and_mrr():
    item = {"evidence": [{"quote": "Alpha beta."}, {"quote": "Gamma delta."}]}
    chunks = [{"content": "nothing"}, {"content": "xx Alpha  beta. yy"}]
    s = retrieval_scores(item, chunks, 3)
    assert s["recall"] == 0.5 and not s["full_hit"] and s["mrr"] == 0.5


def test_aggregate_mean_sd_range_and_single_run():
    from eval.scorer import aggregate
    a = aggregate([{"full_hit@k": 0.86}, {"full_hit@k": 0.90}, {"full_hit@k": 0.88}])["full_hit@k"]
    assert abs(a["mean"] - 0.88) < 1e-9 and abs(a["sd"] - 0.02) < 1e-9
    assert (a["min"], a["max"], a["n"]) == (0.86, 0.90, 3)
    assert aggregate([{"x": 1.0}])["x"]["sd"] == 0.0


def test_noise_flag_and_pm_formatting():
    from eval.run_eval import noise_flag, pm
    lo = {"mean": 0.86, "sd": 0.02, "n": 3}
    assert noise_flag(lo, {"mean": 0.87, "sd": 0.01, "n": 3}) == "within noise"
    assert noise_flag(lo, {"mean": 0.95, "sd": 0.01, "n": 3}) == "up"
    assert noise_flag({"mean": 0.8, "sd": 0.0, "n": 1}, {"mean": 0.9, "sd": 0.0, "n": 1}).startswith("n/a")
    assert pm({"mean": 0.9, "sd": 0.0}) == "0.90" and pm({"mean": 0.9, "sd": 0.02}) == "0.90 ± 0.02"
