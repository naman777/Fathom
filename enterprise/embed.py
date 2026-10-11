"""Open-source embedding models for the enterprise corpus.

Two backends produce the same vectors for the same model:
  - "st":        sentence-transformers on the GPU, used offline to embed the corpus (eval/ and enterprise/ingest.py).
  - "fastembed": ONNX on the CPU, used by the API to embed one query at a time, so the server needs no GPU or PyTorch.

Prefixes are applied here, not by the libraries, so both backends see identical text.
"""
import threading
from functools import lru_cache

from core import config, obs

# model -> (dimension, query prefix, passage prefix). All are 512-token encoders with CLS pooling and cosine similarity.
_BGE_QUERY = "Represent this sentence for searching relevant passages: "
MODELS = {
    "BAAI/bge-small-en-v1.5": (384, _BGE_QUERY, ""),
    "BAAI/bge-base-en-v1.5": (768, _BGE_QUERY, ""),
    "snowflake/snowflake-arctic-embed-m": (768, _BGE_QUERY, ""),
}

_lock = threading.Lock()
_loaded: dict[tuple[str, str], object] = {}


def dim(model: str | None = None) -> int:
    return MODELS[model or config.ENT_EMBED_MODEL][0]


def _load(model: str, backend: str):
    with _lock:
        key = (model, backend)
        if key not in _loaded:
            if backend == "st":
                from sentence_transformers import SentenceTransformer
                m = SentenceTransformer(model)
                m.half()  # fp16: about 2x faster on a 6 GB GPU, no measurable change in ranking
                _loaded[key] = m
            else:
                from fastembed import TextEmbedding
                _loaded[key] = TextEmbedding(model)
        return _loaded[key]


def _encode(texts: list[str], model: str, backend: str, batch_size: int) -> list[list[float]]:
    m = _load(model, backend)
    if backend == "st":
        return m.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False).tolist()
    return [v.tolist() for v in m.embed(texts, batch_size=batch_size)]


def passages(texts: list[str], model: str | None = None, backend: str = "st", batch_size: int = 128) -> list[list[float]]:
    model = model or config.ENT_EMBED_MODEL
    return _encode([MODELS[model][2] + t for t in texts], model, backend, batch_size)


def queries(texts: list[str], model: str | None = None, backend: str = "fastembed", batch_size: int = 64) -> list[list[float]]:
    model = model or config.ENT_EMBED_MODEL
    return _encode([MODELS[model][1] + t for t in texts], model, backend, batch_size)


@lru_cache(maxsize=2048)
def _query_cached(text: str, model: str) -> tuple:
    return tuple(queries([text], model)[0])


def query(text: str) -> list[float]:
    """Cached single-query embedding on the CPU (re-queries are free)."""
    with obs.stage("embed"):
        return list(_query_cached(text, config.ENT_EMBED_MODEL))
