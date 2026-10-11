"""Qdrant vs Postgres + pgvector on the same vectors: ANN recall, filtered search and latency.

    docker run -d --name fathom-pgvector -e POSTGRES_PASSWORD=postgres -p 5433:5432 pgvector/pgvector:pg17
    python -m eval.ent_db_compare [--collection enterprise] [--load]

Both engines get the identical set of chunk vectors (exported from the Qdrant collection) and the identical query
vectors (the benchmark questions). Ground truth is exact cosine top-10 computed in numpy, so "recall" here is how often
the approximate index returns the true nearest neighbours, not answer quality. Each engine is measured unfiltered and
with two role filters (a broad one and a narrow one), because filtering is where vector indexes differ most.
Latency is one query at a time, vector search only (no embedding, no payload text), p50 / p95 / p99.
Writes eval/results/ent_db_compare.json.
"""
import argparse
import json
import os
import time
import uuid

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from qdrant_client import models

from core import config
from enterprise import acl, data, embed, store
from eval.ent_scorer import latency

PG_URL = os.environ.get("PGVECTOR_URL", "postgresql://postgres:postgres@localhost:5433/postgres")
K = 10
FILTERS = {"none": None, "engineer": acl.role_groups("engineer"), "new_hire": acl.role_groups("new_hire")}


def export(collection: str):
    """All points of the collection: ids, doc groups and dense vectors."""
    ids, groups, vecs, offset = [], [], [], None
    while True:
        pts, offset = store.client().scroll(collection, limit=2000, offset=offset, with_payload=["groups"], with_vectors=[store.DENSE])
        for p in pts:
            ids.append(str(p.id))
            groups.append(p.payload["groups"])
            vecs.append(p.vector[store.DENSE])
        print(f"  exported {len(ids)}", end="\r", flush=True)
        if offset is None:
            break
    return ids, groups, np.asarray(vecs, dtype=np.float32)


def load_pg(conn, ids, groups, vecs) -> dict:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("DROP TABLE IF EXISTS ent_chunks")
    conn.execute(f"CREATE TABLE ent_chunks (id uuid PRIMARY KEY, groups text[] NOT NULL, embedding vector({vecs.shape[1]}) NOT NULL)")
    register_vector(conn)
    t = time.time()
    with conn.cursor().copy("COPY ent_chunks (id, groups, embedding) FROM STDIN WITH (FORMAT BINARY)") as cp:
        cp.set_types(["uuid", "text[]", "vector"])
        for i, g, v in zip(ids, groups, vecs):
            cp.write_row((uuid.UUID(i), g, v))
    load_s = time.time() - t
    conn.execute("SET maintenance_work_mem = '1GB'")
    conn.execute("SET max_parallel_maintenance_workers = 4")
    t = time.time()
    conn.execute("CREATE INDEX ent_chunks_hnsw ON ent_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128)")
    hnsw_s = time.time() - t
    conn.execute("CREATE INDEX ent_chunks_groups ON ent_chunks USING gin (groups)")
    conn.execute("ANALYZE ent_chunks")
    size = lambda rel: conn.execute("SELECT pg_total_relation_size(%s)", (rel,)).fetchone()[0]  # noqa: E731
    return {"load_s": round(load_s, 1), "hnsw_build_s": round(hnsw_s, 1), "table_mb": round(size("ent_chunks") / 1e6),
            "hnsw_index_mb": round(conn.execute("SELECT pg_relation_size('ent_chunks_hnsw')").fetchone()[0] / 1e6)}


def exact(vecs, qv, mask):
    idx = np.flatnonzero(mask) if mask is not None else None
    base = vecs[idx] if idx is not None else vecs
    out = []
    for v in qv:
        sims = base @ v
        top = np.argpartition(-sims, K)[:K]
        top = top[np.argsort(-sims[top])]
        out.append((idx[top] if idx is not None else top).tolist())
    return out


def measure(run, qv, truth, ids) -> dict:
    run(qv[0])
    hits, ms, short = [], [], 0
    for v, want in zip(qv, truth):
        t = time.perf_counter()
        got = run(v)
        ms.append((time.perf_counter() - t) * 1000)
        short += len(got) < K
        hits.append(len(set(got) & {ids[i] for i in want}) / K)
    return {"recall@10": round(float(np.mean(hits)), 4), "queries_returning_fewer_than_10": short,
            **{k: round(v, 2) for k, v in latency(ms).items() if k != "n"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default=config.ENT_COLLECTION)
    ap.add_argument("--load", action="store_true", help="(re)load the vectors into Postgres; otherwise reuse the table")
    a = ap.parse_args()

    ids, groups, vecs = export(a.collection)
    print(f"\n{len(ids)} vectors of dimension {vecs.shape[1]}")
    questions = [q["question"] for q in data.questions() if q["expected_doc_ids"]]
    qv = np.asarray(embed.queries(questions), dtype=np.float32)
    out = {"vectors": len(ids), "dim": int(vecs.shape[1]), "queries": len(questions), "k": K, "engines": {}}

    conn = psycopg.connect(PG_URL, autocommit=True)
    if a.load:
        out["pgvector_build"] = load_pg(conn, ids, groups, vecs)
        print("pgvector build:", out["pgvector_build"])
    register_vector(conn)
    info = store.client().get_collection(a.collection)
    out["qdrant_config"] = {"hnsw_m": info.config.hnsw_config.m, "ef_construct": info.config.hnsw_config.ef_construct,
                            "quantization": "int8 scalar, rescored with the original vectors", "sparse_bm25_in_same_collection": True}

    def qdrant(flt, ef=None, exact_search=False):
        params = models.SearchParams(hnsw_ef=ef, exact=exact_search,
                                     quantization=models.QuantizationSearchParams(rescore=True, oversampling=2.0))
        return lambda v: [str(p.id) for p in store.client().query_points(
            a.collection, query=v.tolist(), using=store.DENSE, query_filter=store.group_filter(flt), limit=K,
            search_params=params, with_payload=False).points]

    def pg(flt, ef, iterative):
        conn.execute(f"SET hnsw.ef_search = {ef}")
        conn.execute(f"SET hnsw.iterative_scan = {'relaxed_order' if iterative else 'off'}")
        where = "WHERE groups && %s " if flt is not None else ""
        sql = f"SELECT id FROM ent_chunks {where}ORDER BY embedding <=> %s LIMIT {K}"
        return lambda v: [str(r[0]) for r in conn.execute(sql, ((flt, v) if flt is not None else (v,))).fetchall()]

    for name, flt in FILTERS.items():
        mask = np.array([bool(set(g) & set(flt)) for g in groups]) if flt is not None else None
        truth = exact(vecs, qv, mask)
        share = float(mask.mean()) if mask is not None else 1.0
        row = {"share_of_corpus_visible": round(share, 3)}
        row["qdrant (default ef)"] = measure(qdrant(flt), qv, truth, ids)
        row["qdrant (ef=128)"] = measure(qdrant(flt, ef=128), qv, truth, ids)
        row["pgvector (ef_search=40, default)"] = measure(pg(flt, 40, False), qv, truth, ids)
        row["pgvector (ef_search=128)"] = measure(pg(flt, 128, False), qv, truth, ids)
        if flt is not None:
            row["pgvector (ef_search=40, iterative scan)"] = measure(pg(flt, 40, True), qv, truth, ids)
        out["engines"][name] = row
        print(f"\nfilter={name} (sees {share:.0%} of the corpus)")
        for eng, r in row.items():
            if isinstance(r, dict):
                print(f"  {eng:42} recall@10={r['recall@10']:.3f} p50={r['p50']:.1f} p95={r['p95']:.1f} p99={r['p99']:.1f} ms  short={r['queries_returning_fewer_than_10']}")
    path = config.ROOT / "eval" / "results" / "ent_db_compare.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
