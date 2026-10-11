"""Choose the embedding model and chunk size for the enterprise corpus by measuring them.

    python -m eval.ent_embed_bakeoff --models BAAI/bge-small-en-v1.5 BAAI/bge-base-en-v1.5 --targets 1200 2000
    python -m eval.ent_embed_bakeoff --models openai:text-embedding-3-small      # paid API reference point

Runs on the development subset (eval/ent_subset.py). For each model and chunk size: embed the chunks, embed the 470
questions that have gold documents, rank chunks by exact cosine similarity (no index, so the model is the only variable)
and score at document level. Needs the GPU environment (PyTorch + sentence-transformers). Results are appended to
eval/results/ent_embed_bakeoff.json.
"""
import argparse
import json
import time

import numpy as np

from core import config, llm
from enterprise import data, embed
from eval import ent_subset

KS = (5, 10, 20)


def _openai(texts, model):
    old, config.EMBED_MODEL = config.EMBED_MODEL, model
    try:
        return llm.embed(texts)
    finally:
        config.EMBED_MODEL = old


def embed_all(model: str, texts: list[str], is_query: bool, batch: int):
    if model.startswith("openai:"):
        return np.asarray(_openai(texts, model.split(":", 1)[1]), dtype=np.float32)
    fn = embed.queries if is_query else embed.passages
    out = []
    for i in range(0, len(texts), 4096):  # sorted by length inside encode(); slices keep progress visible
        out.append(np.asarray(fn(texts[i:i + 4096], model, backend="st", batch_size=batch), dtype=np.float32))
        if not is_query:
            print(f"    {min(i + 4096, len(texts))}/{len(texts)}", end="\r", flush=True)
    return np.concatenate(out)


def score(qv: np.ndarray, cv: np.ndarray, chunk_docs: list[str], questions: list[dict]) -> dict:
    out = {f"recall@{k}": [] for k in KS} | {"mrr@20": [], "full_hit@10": []}
    for q, v in zip(questions, qv):
        sims = cv @ v
        top = np.argpartition(-sims, 200)[:200]
        top = top[np.argsort(-sims[top])]
        docs = list(dict.fromkeys(chunk_docs[i] for i in top))  # document ranking: best chunk per document
        gold = set(q["expected_doc_ids"])
        for k in KS:
            out[f"recall@{k}"].append(len(gold & set(docs[:k])) / len(gold))
        out["full_hit@10"].append(gold <= set(docs[:10]))
        out["mrr@20"].append(next((1 / (i + 1) for i, d in enumerate(docs[:20]) if d in gold), 0.0))
    return {k: round(float(np.mean(v)), 4) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=list(embed.MODELS))
    ap.add_argument("--targets", nargs="+", type=int, default=[1200])
    ap.add_argument("--per-mille", type=int, default=60)
    ap.add_argument("--batch", type=int, default=128)
    a = ap.parse_args()

    questions = [q for q in data.questions() if q["expected_doc_ids"]]
    path = config.ROOT / "eval" / "results" / "ent_embed_bakeoff.json"
    results = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    docs = list(ent_subset.documents(a.per_mille))
    print(f"{len(docs)} documents, {len(questions)} questions")
    for target in a.targets:
        chunks = [c for d in docs for c in ent_subset.chunks_of(d, target, overlap=target // 6)]
        texts, chunk_docs = [c["text"] for c in chunks], [c["doc_id"] for c in chunks]
        print(f"chunk target {target}: {len(chunks)} chunks, {sum(map(len, texts)) / len(texts):.0f} chars mean")
        for model in a.models:
            print(f"  {model}")
            t = time.time()
            cv = embed_all(model, texts, False, a.batch)
            secs = time.time() - t
            t = time.time()
            qv = embed_all(model, [q["question"] for q in questions], True, a.batch)
            row = {"model": model, "chunk_target": target, "documents": len(docs), "chunks": len(chunks), "dim": int(cv.shape[1]),
                   "chunks_per_s": round(len(chunks) / secs, 1), "query_ms_batched": round((time.time() - t) * 1000 / len(questions), 2),
                   **score(qv, cv, chunk_docs, questions)}
            print("   ", {k: v for k, v in row.items() if k not in ("model", "documents")})
            results = [r for r in results if (r["model"], r["chunk_target"], r["documents"]) != (model, target, len(docs))] + [row]
            path.write_text(json.dumps(results, indent=2), encoding="utf-8")
            del cv


if __name__ == "__main__":
    main()
