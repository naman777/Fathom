"""Development subset of the enterprise corpus: every gold document plus a deterministic sample of the rest.

Experiments that compare options (embedding model, chunk size, vector database) run on this subset because embedding
512k documents once per option is hours of GPU time. With far fewer distractors than the full corpus, retrieval is
easier here, so subset numbers are for *relative* comparison only and are never reported as benchmark scores.
"""
import hashlib

from enterprise import acl, chunking, data


def gold_ids() -> set[str]:
    return {d for q in data.questions() for d in q["expected_doc_ids"]}


def in_sample(doc_id: str, per_mille: int) -> bool:
    """Stable across runs and machines (Python's hash() is salted per process)."""
    return int(hashlib.md5(doc_id.encode()).hexdigest()[:8], 16) % 1000 < per_mille


def documents(per_mille: int = 60):
    """Gold documents plus about per_mille/1000 of the corpus (60 is roughly 31k documents)."""
    gold = gold_ids()
    for d in data.iter_documents():
        if d["doc_id"] in gold or in_sample(d["doc_id"], per_mille):
            yield d


def chunks_of(doc: dict, target: int = 1200, overlap: int = 200) -> list[dict]:
    groups = acl.groups_for(doc["source_type"], doc["title"])
    return [{"doc_id": doc["doc_id"], "source": doc["source_type"], "title": doc["title"] or "", "pos": i, "text": t,
             "groups": groups}
            for i, t in enumerate(chunking.chunk(doc["source_type"], doc["title"], doc["content"], target, overlap))]
