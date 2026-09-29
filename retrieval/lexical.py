import re


def _terms(query: str) -> list[str]:
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z0-9]{2,}", query.lower()):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def search(conn, query: str, k: int = 20, doc_ids=None):
    """Postgres full-text search; OR-semantics so long natural questions still match."""
    terms = _terms(query)
    if not terms:
        return []
    params = [" | ".join(terms)]
    filt = ""
    if doc_ids:
        filt = "AND c.document_id = ANY(%s)"
        params.append(list(doc_ids))
    params.append(k)
    rows = conn.execute(f"""
        WITH q AS (SELECT to_tsquery('english', %s) AS tq)
        SELECT c.id, c.document_id, d.title, c.position, c.content,
               ts_rank_cd(c.tsv, q.tq) AS score
        FROM chunks c JOIN documents d ON d.id = c.document_id, q
        WHERE c.tsv @@ q.tq {filt}
        ORDER BY score DESC LIMIT %s""", params).fetchall()
    return [dict(id=r[0], document_id=r[1], title=r[2], position=r[3], content=r[4], score=float(r[5]))
            for r in rows]
