import json
import threading
from collections import defaultdict
from functools import lru_cache

from openai import OpenAI

from core import config

_client = None

# Token accounting for cost visibility: {model: [prompt_tokens, completion_tokens, calls]} (process-wide, thread-safe).
USAGE: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
_usage_lock = threading.Lock()


def _record(model: str, usage) -> None:
    if usage is None:
        return
    with _usage_lock:
        u = USAGE[model]
        u[0] += getattr(usage, "prompt_tokens", 0) or 0
        u[1] += getattr(usage, "completion_tokens", 0) or 0
        u[2] += 1


def usage_snapshot() -> dict[str, list[int]]:
    with _usage_lock:
        return {m: list(v) for m, v in USAGE.items()}


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
        _record(config.EMBED_MODEL, r.usage)
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
    _record(model, r.usage)
    return r.choices[0].message.content or ""


def chat_stream(messages, temperature=None, max_tokens=1500, model=None):
    model = model or config.CHAT_MODEL
    s = client().chat.completions.create(model=model, messages=messages, stream=True,
                                         stream_options={"include_usage": True}, **_params(model, max_tokens))
    for ev in s:
        _record(model, getattr(ev, "usage", None))
        if ev.choices and ev.choices[0].delta.content:
            yield ev.choices[0].delta.content


def chat_json(messages, **kw) -> dict:
    try:
        return json.loads(chat(messages, json_mode=True, **kw))
    except json.JSONDecodeError:
        return {}
