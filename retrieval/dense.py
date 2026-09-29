from core import llm, obs


def search(conn, query: str, k: int = 20, doc_ids=None):
    qv = llm.embed_query(query)
    filt = "WHERE c.document_id = ANY(%s)" if doc_ids else ""
    params = [qv] + ([list(doc_ids)] if doc_ids else []) + [qv, k]
    with obs.stage("dense"):
        rows = conn.execute(f"""
        SELECT c.id, c.document_id, d.title, c.position, c.content,
               1 - (c.embedding <=> %s::vector) AS score
        FROM chunks c JOIN documents d ON d.id = c.document_id
        {filt}
        ORDER BY c.embedding <=> %s::vector LIMIT %s""", params).fetchall()
    return [dict(id=r[0], document_id=r[1], title=r[2], position=r[3], content=r[4], score=float(r[5]))
            for r in rows]
