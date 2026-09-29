import re
import statistics

from core import llm


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_#>`]", "", s)).strip().lower()


def _has(chunk_text: str, quote: str) -> bool:
    return norm(quote) in norm(chunk_text)


def retrieval_scores(item: dict, chunks: list[dict], k: int) -> dict:
    top = chunks[:k]
    quotes = [e["quote"] for e in item["evidence"]]
    found = [any(_has(c["content"], q) for c in top) for q in quotes]
    relevant = [any(_has(c["content"], q) for q in quotes) for c in top]
    return {
        "recall": sum(found) / len(found),          # fraction of evidence quotes covered
        "full_hit": all(found),                      # every needed passage retrieved
        "precision": (sum(relevant) / len(top)) if top else 0.0,
        "mrr": next((1 / (i + 1) for i, r in enumerate(relevant) if r), 0.0),
    }


JUDGE_SYS = (
    "You grade a RAG answer. Given sources, a question, a gold answer and the model answer, return JSON: "
    "{\"correct\": true|false (matches gold answer in substance), "
    "\"claims\": <int number of factual claims in the answer>, "
    "\"unsupported\": <int claims NOT supported by the sources>}. "
    "If the answer correctly says the sources lack the info, claims=0."
)


def judge(item: dict, chunks: list[dict], answer: str) -> dict:
    src = "\n\n".join(f"[{i}] {c['content']}" for i, c in enumerate(chunks, 1))
    r = llm.chat_json([{"role": "system", "content": JUDGE_SYS},
                       {"role": "user", "content":
                        f"Sources:\n{src}\n\nQuestion: {item['question']}\nGold: {item['answer']}\nAnswer: {answer}"}],
                      max_tokens=100)
    claims = max(int(r.get("claims", 0) or 0), 0)
    uns = min(max(int(r.get("unsupported", 0) or 0), 0), claims)
    return {"correct": bool(r.get("correct")), "claims": claims, "unsupported": uns}


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def summarize(rows: list[dict]) -> dict:
    m = statistics.mean
    out = {
        "n": len(rows),
        "recall@k": m(r["recall"] for r in rows),
        "full_hit@k": m(r["full_hit"] for r in rows),
        "precision@k": m(r["precision"] for r in rows),
        "mrr": m(r["mrr"] for r in rows),
        "retrieval_ms_p50": pct([r["ms"] for r in rows], 50),
        "retrieval_ms_p95": pct([r["ms"] for r in rows], 95),
    }
    gen = [r for r in rows if "correct" in r]
    if gen:
        claims = sum(r["claims"] for r in gen)
        out["answer_accuracy"] = m(r["correct"] for r in gen)
        out["unsupported_claim_rate"] = (sum(r["unsupported"] for r in gen) / claims) if claims else 0.0
        out["first_token_ms_p50"] = pct([r["first_token_ms"] for r in gen], 50)
        out["first_token_ms_p95"] = pct([r["first_token_ms"] for r in gen], 95)
        out["e2e_ms_p50"] = pct([r["e2e_ms"] for r in gen], 50)
        out["e2e_ms_p95"] = pct([r["e2e_ms"] for r in gen], 95)
    return out
