"""Bulk-load the enterprise corpus into Qdrant: chunk, embed on the GPU, add BM25 sparse vectors, upsert.

    python -m enterprise.ingest --recreate                 # full corpus (about 512k documents; hours on a laptop GPU)
    python -m enterprise.ingest --per-mille 60 --collection enterprise_dev --recreate   # development subset
    python -m enterprise.ingest                            # resume after an interruption

Run it with the GPU environment (PyTorch + sentence-transformers). Resumable: the dataset has a fixed order, so progress
is one number (documents done) in a checkpoint file next to the data, and point ids are deterministic, so a batch that
is sent twice overwrites itself. HNSW indexing is switched off during the load and back on at the end, which is much
faster than indexing incrementally.
"""
import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

from qdrant_client import models

from core import config
from enterprise import data, embed, store
from eval import ent_subset


def _checkpoint(collection: str) -> Path:
    return Path(config.ENT_DATA_DIR) / f"ingest_{collection}.json"


def set_indexing(collection: str, on: bool) -> None:
    store.client().update_collection(collection, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000 if on else 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default=config.ENT_COLLECTION)
    ap.add_argument("--model", default=config.ENT_EMBED_MODEL)
    ap.add_argument("--target", type=int, default=config.ENT_CHUNK_TARGET)
    ap.add_argument("--per-mille", type=int, default=1000, help="1000 = everything; lower = gold documents plus a sample")
    ap.add_argument("--recreate", action="store_true")
    ap.add_argument("--batch", type=int, default=128, help="GPU batch size")
    ap.add_argument("--flush", type=int, default=2048, help="chunks per embed + upsert round")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many documents (0 = no limit)")
    ap.add_argument("--backend", default="st", choices=["st", "fastembed"], help="st = GPU, fastembed = CPU (slow; small tests only)")
    a = ap.parse_args()

    if sys.platform == "win32":  # a full load takes hours: keep Windows from idle-sleeping while this process runs
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

    ck = _checkpoint(a.collection)
    if a.recreate:
        ck.unlink(missing_ok=True)
    state = json.loads(ck.read_text()) if ck.exists() else {"docs_seen": 0, "docs": 0, "chunks": 0}
    store.create(a.collection, dim=embed.dim(a.model), recreate=a.recreate)
    set_indexing(a.collection, False)
    gold = ent_subset.gold_ids() if a.per_mille < 1000 else set()
    total = data.count_documents()
    print(f"collection={a.collection} model={a.model} target={a.target} resume_from={state['docs_seen']}/{total}")

    buf: list[dict] = []
    t0, done0 = time.time(), state["chunks"]

    def flush(seen: int):
        if buf:
            store.upsert(buf, embed.passages([c["text"] for c in buf], a.model, backend=a.backend, batch_size=a.batch), a.collection)
            state["chunks"] += len(buf)
            buf.clear()
        state["docs_seen"] = seen
        ck.write_text(json.dumps(state))
        rate = (state["chunks"] - done0) / max(time.time() - t0, 1e-6)
        left = (total - seen) / max(seen - start, 1) * (time.time() - t0)
        print(f"  {seen}/{total} docs scanned, {state['docs']} indexed, {state['chunks']} chunks, {rate:.0f} chunks/s, "
              f"about {left / 60:.0f} min left   ", end="\r", flush=True)

    start = state["docs_seen"]
    seen = 0
    for seen, d in enumerate(data.iter_documents(), 1):
        if seen <= start:
            continue
        if a.per_mille >= 1000 or d["doc_id"] in gold or ent_subset.in_sample(d["doc_id"], a.per_mille):
            buf.extend(ent_subset.chunks_of(d, a.target, a.target // 6))
            state["docs"] += 1
        if len(buf) >= a.flush:  # only at document boundaries, so a resume never splits a document
            flush(seen)
        if a.limit and state["docs"] >= a.limit:
            break
    flush(seen)
    set_indexing(a.collection, True)
    info = store.client().get_collection(a.collection)
    print(f"\ndone: {state['docs']} documents, {state['chunks']} chunks in {(time.time() - t0) / 60:.1f} min; "
          f"collection has {info.points_count} points, status {info.status}")


if __name__ == "__main__":
    main()
