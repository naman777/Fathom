"""Local ONNX cross-encoder reranker (fastembed): no API call, no GPU, runs in tens of milliseconds."""
import threading

from core import config

_model = None
_lock = threading.Lock()


def _get():
    global _model
    with _lock:
        if _model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            _model = TextCrossEncoder(model_name=config.LOCAL_RERANK_MODEL)
    return _model


def warmup():
    _get()


def rerank(query: str, candidates: list[dict], top: int = 6, max_candidates: int | None = None) -> list[dict]:
    cands = candidates[: max_candidates or config.LOCAL_RERANK_CANDIDATES]
    if len(cands) <= 1:
        return cands[:top]
    scores = list(_get().rerank(query, [c["content"] for c in cands]))
    order = sorted(range(len(cands)), key=lambda i: (-scores[i], i))
    return [{**cands[i], "rerank_score": float(scores[i])} for i in order[:top]]
