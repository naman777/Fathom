import re

from core import config, obs

MODES = ("or", "or_norm", "websearch", "trigram")


def _terms(query: str) -> list[str]:
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z0-9]{2,}", query.lower()):
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _row(r):
    return dict(id=r[0], document_id=r[1], title=r[2], position=r[3], content=r[4], score=float(r[5]))


def _fts(conn, tsquery_sql: str, tsquery_arg: str, k: int, doc_ids, norm: int = 0):
    params = [tsquery_arg]
    filt = ""
    if doc_ids:
        filt = "AND c.document_id = ANY(%s)"
        params.append(list(doc_ids))
    params.append(k)
    return [_row(r) for r in conn.execute(f"""
        WITH q AS (SELECT {tsquery_sql} AS tq)
        SELECT c.id, c.document_id, d.title, c.position, c.content,
               ts_rank_cd(c.tsv, q.tq, {int(norm)}) AS score
        FROM chunks c JOIN documents d ON d.id = c.document_id, q
        WHERE c.tsv @@ q.tq {filt}
        ORDER BY score DESC LIMIT %s""", params).fetchall()]


def search(conn, query: str, k: int = 20, doc_ids=None, mode: str | None = None):
    """Lexical search over chunks. Modes (config.LEXICAL_MODE):
      or         OR of every term, ranked by ts_rank_cd (default; long natural questions still match)
      or_norm    same, but ranks are divided by 1 + log(chunk length) so long chunks are not favoured
      websearch  websearch_to_tsquery (AND of terms, quoted phrases and -negation honoured), topped up with the OR
                 result when it returns fewer than k rows
      trigram    pg_trgm word_similarity of the query against the chunk (typo-tolerant; needs the pg_trgm extension)
    """
    mode = mode or config.LEXICAL_MODE
    terms = _terms(query)
    if not terms:
        return []
    with obs.stage("lexical"):
        or_arg = " | ".join(terms)
        if mode == "or":
            return _fts(conn, "to_tsquery('english', %s)", or_arg, k, doc_ids)
        if mode == "or_norm":
            return _fts(conn, "to_tsquery('english', %s)", or_arg, k, doc_ids, norm=1)
        if mode == "websearch":
            hits = _fts(conn, "websearch_to_tsquery('english', %s)", query, k, doc_ids)
            if len(hits) < k:
                have = {h["id"] for h in hits}
                hits += [h for h in _fts(conn, "to_tsquery('english', %s)", or_arg, k, doc_ids) if h["id"] not in have]
            return hits[:k]
        if mode == "trigram":
            params = [query, query] + ([list(doc_ids)] if doc_ids else []) + [k]
            filt = "AND c.document_id = ANY(%s)" if doc_ids else ""
            return [_row(r) for r in conn.execute(f"""
                SELECT c.id, c.document_id, d.title, c.position, c.content, word_similarity(%s, c.content) AS score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE %s <%% c.content {filt}
                ORDER BY score DESC LIMIT %s""", params).fetchall()]
        raise ValueError(f"unknown lexical mode {mode!r}; choose from {MODES}")
