import json
from functools import lru_cache

from openai import OpenAI

from core import config

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 96):
        batch = [t.replace("\n", " ")[:8000] for t in texts[i:i + 96]]
        r = client().embeddings.create(model=config.EMBED_MODEL, input=batch)
        out.extend(d.embedding for d in r.data)
    return out


@lru_cache(maxsize=2048)
def _embed_cached(text: str) -> tuple:
    return tuple(embed([text])[0])


def embed_query(text: str) -> list[float]:
    """Cached single-query embedding (re-queries are free)."""
    return list(_embed_cached(text))


def _is_reasoning(model: str) -> bool:
    return model.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def _params(model: str, max_tokens: int) -> dict:
    """Reasoning families (gpt-5/6, o-series) take max_completion_tokens (which also covers hidden reasoning
    tokens), reject custom temperature and accept reasoning_effort. Other models use max_tokens."""
    if _is_reasoning(model):
        return {"max_completion_tokens": max_tokens + 1500, "reasoning_effort": config.REASONING_EFFORT}
    return {"max_tokens": max_tokens, "temperature": 0.1}


def chat(messages, json_mode=False, temperature=None, max_tokens=1200, model=None) -> str:
    # `temperature` kept for call-site compatibility; it is fixed per model family (see _params).
    model = model or config.CHAT_MODEL
    kw = {"response_format": {"type": "json_object"}} if json_mode else {}
    r = client().chat.completions.create(model=model, messages=messages, **_params(model, max_tokens), **kw)
    return r.choices[0].message.content or ""


def chat_stream(messages, temperature=None, max_tokens=1500, model=None):
    model = model or config.CHAT_MODEL
    s = client().chat.completions.create(model=model, messages=messages, stream=True, **_params(model, max_tokens))
    for ev in s:
        if ev.choices and ev.choices[0].delta.content:
            yield ev.choices[0].delta.content


def chat_json(messages, **kw) -> dict:
    try:
        return json.loads(chat(messages, json_mode=True, **kw))
    except json.JSONDecodeError:
        return {}
