"""Qdrant storage for the enterprise corpus: one collection with a dense vector and a BM25 sparse vector per chunk.

Why Qdrant here (the upload side stays on Postgres + pgvector): the role filter is applied inside the HNSW traversal
(filterable HNSW with payload indexes) instead of after it, vectors are scalar-quantized to 1 byte per dimension in RAM
with the originals on disk for rescoring, and dense + sparse search with RRF fusion is a single request.

Payload per point: doc_id, source, title, pos (chunk index in the document), text, groups (who may read it).
"""
import uuid
from functools import lru_cache

from qdrant_client import QdrantClient, models

from core import config, obs
from enterprise import embed

DENSE, SPARSE = "dense", "bm25"
_NS = uuid.UUID("6f1d3c52-8f0e-4b57-9a65-2a3b1c9d7e10")


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    # gRPC keeps one multiplexed connection open. Over REST each request opened a new socket here, and a burst of
    # concurrent searches ran Windows out of ephemeral ports (WinError 10048).
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=120, prefer_grpc=config.QDRANT_GRPC)


def point_id(doc_id: str, pos: int) -> str:
    """Deterministic, so re-running an ingest overwrites instead of duplicating."""
    return str(uuid.uuid5(_NS, f"{doc_id}:{pos}"))


def create(collection: str | None = None, dim: int | None = None, recreate: bool = False, quantize: bool = True) -> None:
    c, name = client(), collection or config.ENT_COLLECTION
    if c.collection_exists(name):
        if not recreate:
            return
        c.delete_collection(name)
    c.create_collection(
        name,
        vectors_config={DENSE: models.VectorParams(size=dim or embed.dim(), distance=models.Distance.COSINE, on_disk=True)},
        sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},  # IDF applied by Qdrant
        quantization_config=models.ScalarQuantization(scalar=models.ScalarQuantizationConfig(
            type=models.ScalarType.INT8, quantile=0.99, always_ram=True)) if quantize else None,
        hnsw_config=models.HnswConfigDiff(m=16, ef_construct=128),
        on_disk_payload=True,
    )
    for field in ("groups", "source", "doc_id"):  # payload indexes make the role filter part of the graph search
        c.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)


@lru_cache(maxsize=1)
def _bm25():
    from fastembed import SparseTextEmbedding
    return SparseTextEmbedding("Qdrant/bm25")


def sparse_passages(texts: list[str]) -> list[models.SparseVector]:
    return [models.SparseVector(indices=v.indices.tolist(), values=v.values.tolist()) for v in _bm25().embed(texts)]


def sparse_query(text: str) -> models.SparseVector:
    v = next(iter(_bm25().query_embed(text)))
    return models.SparseVector(indices=v.indices.tolist(), values=v.values.tolist())


def upsert(chunks: list[dict], vectors: list[list[float]], collection: str | None = None) -> None:
    """chunks: dicts with doc_id, source, title, pos, text, groups."""
    sparse = sparse_passages([c["text"] for c in chunks])
    points = [models.PointStruct(id=point_id(c["doc_id"], c["pos"]), vector={DENSE: v, SPARSE: s},
                                 payload={k: c[k] for k in ("doc_id", "source", "title", "pos", "text", "groups")})
              for c, v, s in zip(chunks, vectors, sparse)]
    for i in range(0, len(points), 256):  # Qdrant rejects request bodies over 32 MB; 256 points of 768 floats is about 5 MB
        client().upsert(collection or config.ENT_COLLECTION, wait=False, points=points[i:i + 256])


def group_filter(groups: list[str] | None, sources: list[str] | None = None) -> models.Filter | None:
    """groups=None means unrestricted (evaluation only). An empty list matches nothing."""
    must = []
    if groups is not None:
        must.append(models.FieldCondition(key="groups", match=models.MatchAny(any=list(groups))))
    if sources:
        must.append(models.FieldCondition(key="source", match=models.MatchAny(any=list(sources))))
    return models.Filter(must=must) if must else None


def _hit(p) -> dict:
    pl = p.payload
    return {"id": str(p.id), "doc_id": pl["doc_id"], "source": pl["source"], "title": pl["title"], "position": pl["pos"],
            "content": pl["text"], "score": float(getattr(p, "score", 0.0) or 0.0)}  # scroll records have no score


def search(query: str, groups: list[str] | None, k: int = 20, mode: str = "hybrid", sources: list[str] | None = None,
           vector: list[float] | None = None, collection: str | None = None, exact: bool = False) -> list[dict]:
    """mode: dense | lexical | hybrid (RRF inside Qdrant). The same filter is applied to every leg."""
    name, flt = collection or config.ENT_COLLECTION, group_filter(groups, sources)
    params = models.SearchParams(exact=exact, quantization=models.QuantizationSearchParams(rescore=True, oversampling=2.0))
    if mode != "lexical" and vector is None:
        vector = embed.query(query)
    with obs.stage("dense" if mode == "dense" else "lexical" if mode == "lexical" else "hybrid"):
        if mode == "dense":
            res = client().query_points(name, query=vector, using=DENSE, query_filter=flt, limit=k, search_params=params,
                                        with_payload=True)
        elif mode == "lexical":
            res = client().query_points(name, query=sparse_query(query), using=SPARSE, query_filter=flt, limit=k,
                                        with_payload=True)
        else:
            res = client().query_points(name, prefetch=[
                models.Prefetch(query=vector, using=DENSE, filter=flt, limit=k, params=params),
                models.Prefetch(query=sparse_query(query), using=SPARSE, filter=flt, limit=k),
            ], query=models.FusionQuery(fusion=models.Fusion.RRF), limit=k, with_payload=True)
    return [_hit(p) for p in res.points]


def neighbours(hits: list[dict], groups: list[str] | None, n: int = 1, collection: str | None = None) -> dict[tuple[str, int], str]:
    """Text of the chunks within n positions of each hit, keyed by (doc_id, position), in one request and under the
    same role filter as the search itself."""
    if not hits:
        return {}
    flt = group_filter(groups) or models.Filter()
    flt.should = [models.Filter(must=[
        models.FieldCondition(key="doc_id", match=models.MatchValue(value=h["doc_id"])),
        models.FieldCondition(key="pos", range=models.Range(gte=h["position"] - n, lte=h["position"] + n))]) for h in hits]
    pts, _ = client().scroll(collection or config.ENT_COLLECTION, scroll_filter=flt, limit=len(hits) * (2 * n + 1),
                             with_payload=["doc_id", "pos", "text"])
    return {(p.payload["doc_id"], p.payload["pos"]): p.payload["text"] for p in pts}
