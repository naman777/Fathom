import sys
import time

from core import config
from retrieval import dense, fuse, hyde, lexical, rerank as rr, rerank_local


def hybrid(conn, query: str, k: int = 6, candidates: int = 20, rerank: bool = True,
           mode: str = "hybrid", doc_ids=None) -> list[dict]:
    """mode: lexical | dense | hybrid (RRF). Optionally LLM-rerank the fused candidates.
    With config.HYDE the dense leg searches with a hypothetical-answer embedding (retrieval/hyde.py)."""
    lists = []
    if mode in ("lexical", "hybrid"):
        lists.append(lexical.search(conn, query, candidates, doc_ids))
    if mode in ("dense", "hybrid"):
        vector = hyde.query_vector(query) if config.HYDE else None
        lists.append(dense.search(conn, query, candidates, doc_ids, vector=vector))
    fused = fuse.rrf(lists, top=candidates) if len(lists) > 1 else lists[0]
    if rerank:
        if config.RERANKER == "local":
            return rerank_local.rerank(query, fused[:candidates], top=k)
        return rr.rerank(query, fused[:candidates], top=k)
    return fused[:k]


if __name__ == "__main__":
    from core import db
    q = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "test"
    if "--hyde" in sys.argv:
        config.HYDE = True
    with db.connect() as c:
        t = time.time()
        for r in hybrid(c, q, rerank="--rerank" in sys.argv):
            print(f"{r['score']:.4f} [{r['title']}#{r['position']}] {r['content'][:110]!r}")
        print(f"{(time.time()-t)*1000:.0f} ms")
