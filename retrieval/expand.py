"""Parent-document expansion ("small to big"): match on small chunks, hand the answer model their neighbours.

A hit is often the right passage minus the sentence just before or after it. `expand` fetches the chunks at
position +-radius in the same document and merges them into the hit (chunks overlap by config.CHUNK_OVERLAP characters,
so the shared text is removed when joining). Citation numbering is unchanged: one source per hit, just longer.
"""
from ingest.context import strip_header


def merge(a: str, b: str, max_overlap: int = 400) -> str:
    """Join two consecutive chunks, dropping the text that the chunker repeated at the boundary."""
    for o in range(min(max_overlap, len(a), len(b)), 20, -1):
        if a.endswith(b[:o]):
            return a + b[o:]
    return a + "\n" + b


def expand(conn, chunks: list[dict], radius: int = 1) -> list[dict]:
    if radius <= 0 or not chunks:
        return chunks
    clauses, params = [], []
    for c in chunks:
        clauses.append("(document_id = %s AND position BETWEEN %s AND %s)")
        params += [c["document_id"], c["position"] - radius, c["position"] + radius]
    rows = conn.execute(f"SELECT document_id, position, content FROM chunks WHERE {' OR '.join(clauses)}", params).fetchall()
    by_pos = {(d, p): t for d, p, t in rows}
    out = []
    for c in chunks:
        text = c["content"]
        for step in range(1, radius + 1):
            prev = by_pos.get((c["document_id"], c["position"] - step))
            nxt = by_pos.get((c["document_id"], c["position"] + step))
            if prev:
                text = merge(strip_header(prev), text)
            if nxt:
                text = merge(text, strip_header(nxt))
        out.append({**c, "content": text, "expanded": text != c["content"]})
    return out
