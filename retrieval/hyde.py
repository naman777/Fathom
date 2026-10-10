"""HyDE (Hypothetical Document Embeddings, Gao et al. 2022) for the dense leg.

A question and the passage that answers it are worded differently, so their embeddings sit further apart than two
passages on the same topic. HyDE asks a model to write the passage a document *would* contain, and searches with the
embedding of that text instead. The facts in it may be invented; only its vocabulary and shape matter, and it is never
shown to the user or to the answer model.

The search vector is the mean of the question and hypothetical-passage embeddings (the paper's variant that keeps the
query in the average), which limits the damage when the model drifts off topic. Lexical search and the reranker keep
using the original question.
"""
from functools import lru_cache

from core import config, llm, obs

SYSTEM = (
    "Write a short passage (3-5 sentences) of the kind found in a reference document that directly answers the "
    "question. State the answer as plain fact, using the specific terms such a document would use. If you do not know "
    "the answer, invent plausible specifics rather than hedging. Output only the passage: no preamble, no questions."
)


@lru_cache(maxsize=2048)
def _generate_cached(query: str, model: str) -> str:
    return llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": query}],
                    max_tokens=250, model=model).strip()


def generate(query: str) -> str:
    """Hypothetical answer passage for `query` (cached per query); "" when the model call fails."""
    with obs.stage("hyde"):
        try:
            return _generate_cached(query, config.HYDE_MODEL)
        except Exception:  # noqa: BLE001 - an optional upgrade must not take search down with it
            return ""


def query_vector(query: str) -> list[float]:
    """Embedding to search with: mean of the question and its hypothetical passage, or the question alone on failure."""
    qv = llm.embed_query(query)
    doc = generate(query)
    if not doc:
        return qv
    dv = llm.embed_query(doc)
    return [(a + b) / 2 for a, b in zip(qv, dv)]  # cosine distance ignores the lost unit length
