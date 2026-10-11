"""Role-aware retrieval over the enterprise corpus: hybrid search in Qdrant, then the shared LLM reranker.

Every function takes the caller's role. The role becomes a group filter inside the Qdrant query, and the same filter is
used for neighbour expansion and for each of the agent's sub-queries, so there is no path to a chunk that skips it.
"""
import sys
import time

from core import config
from enterprise import acl, store
from retrieval import rerank as rr
from retrieval.expand import merge


def search(query: str, role: str | None, k: int = 6, candidates: int = 20, rerank: bool = True, mode: str = "hybrid",
           collection: str | None = None) -> list[dict]:
    hits = store.search(query, acl.role_groups(role), k=candidates, mode=mode, collection=collection)
    if rerank:
        return rr.rerank(query, hits, top=k)
    return hits[:k]


def _body(text: str) -> str:
    """Chunk text without its "[Source | title]" first line."""
    return text.split("\n", 1)[1] if text.startswith("[") and "\n" in text else text


def expand(chunks: list[dict], role: str | None, radius: int = 1, collection: str | None = None) -> list[dict]:
    """Widen each hit with the chunks before and after it in the same document (same role filter)."""
    if radius <= 0:
        return chunks
    out, by_pos = [], store.neighbours(chunks, acl.role_groups(role), radius, collection)
    for c in chunks:
        near = {pos: text for (doc, pos), text in by_pos.items() if doc == c["doc_id"]}
        text = c["content"]
        for step in range(1, radius + 1):
            if c["position"] + step in near:
                text = merge(text, _body(near[c["position"] + step]))
            if c["position"] - step in near:
                head, body = (text.split("\n", 1) + [""])[:2] if text.startswith("[") else ("", text)
                joined = merge(_body(near[c["position"] - step]), body)
                text = f"{head}\n{joined}" if head else joined
        out.append({**c, "content": text, "expanded": text != c["content"]})
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    role = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--role=")), "admin")
    t = time.time()
    for r in search(" ".join(args) or "test", role, rerank="--rerank" in sys.argv):
        print(f"{r['score']:.4f} [{r['source']}] {r['title'][:50]!r}#{r['position']} {r['content'][:100]!r}")
    print(f"{(time.time() - t) * 1000:.0f} ms, role={role} groups={acl.role_groups(role)}, collection={config.ENT_COLLECTION}")
