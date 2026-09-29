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


def _params(max_tokens: int) -> dict:
    """gpt-6 family: max_completion_tokens (covers reasoning tokens), no custom temperature."""
    return {"max_completion_tokens": max_tokens + 1500, "reasoning_effort": config.REASONING_EFFORT}


def chat(messages, json_mode=False, temperature=None, max_tokens=1200) -> str:
    # `temperature` kept for call-site compatibility; the model only supports its default.
    kw = {"response_format": {"type": "json_object"}} if json_mode else {}
    r = client().chat.completions.create(
        model=config.CHAT_MODEL, messages=messages, **_params(max_tokens), **kw)
    return r.choices[0].message.content or ""


def chat_stream(messages, temperature=None, max_tokens=1500):
    s = client().chat.completions.create(
        model=config.CHAT_MODEL, messages=messages, stream=True, **_params(max_tokens))
    for ev in s:
        if ev.choices and ev.choices[0].delta.content:
            yield ev.choices[0].delta.content


def chat_json(messages, **kw) -> dict:
    try:
        return json.loads(chat(messages, json_mode=True, **kw))
    except json.JSONDecodeError:
        return {}
