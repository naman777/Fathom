"""Per-request observability: trace id, stage timings, token usage and cost.

A Trace is activated around each chat request (`activate`). LLM calls (core/llm.py) and timed stages (`stage`) attach
themselves to the active trace through a contextvar, so eval scripts and CLIs that never activate one pay nothing.
Every finished request is logged as one JSON line (logger `fathom.request`) and kept in a small in-memory ring buffer
that backs GET /api/stats.

Stage times are *summed busy time*: parallel sub-queries overlap, so stage totals can exceed wall-clock time. Shares
are computed against the sum of the leaf stages, so they always add to 100%.
"""
import contextvars
import json
import logging
import statistics
import sys
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager

from core import config

log = logging.getLogger("fathom.request")
_current: contextvars.ContextVar["Trace | None"] = contextvars.ContextVar("fathom_trace", default=None)
RECENT: deque = deque(maxlen=200)

# Stages that do not contain other stages; shares are computed over these.
LEAF = ("embed", "hyde", "lexical", "dense", "rerank", "plan", "reflect", "answer")


def cost_of(usage: dict[str, list[int]], prices: dict | None = None) -> tuple[float, list[str]]:
    """usage: {model: [prompt_tokens, completion_tokens, calls]}; prices: {model: [usd_per_1m_in, usd_per_1m_out]}.
    Returns (usd for the priced models, models with no configured price)."""
    prices = config.MODEL_PRICES if prices is None else prices
    usd, unpriced = 0.0, []
    for model, (pt, ct, _calls) in usage.items():
        p = prices.get(model)
        if p is None:
            unpriced.append(model)
        else:
            usd += pt / 1e6 * p[0] + ct / 1e6 * p[1]
    return usd, sorted(unpriced)


class Trace:
    def __init__(self, question_chars: int = 0, **attrs):
        self.trace_id = uuid.uuid4().hex[:12]
        self.t0 = time.perf_counter()
        self.question_chars = question_chars
        self.attrs = attrs
        self.usage: dict[str, list[int]] = {}
        self.stages: dict[str, float] = {}
        self.first_token_ms: int | None = None
        self._lock = threading.Lock()

    def add_usage(self, model: str, prompt: int, completion: int) -> None:
        with self._lock:
            u = self.usage.setdefault(model, [0, 0, 0])
            u[0] += prompt
            u[1] += completion
            u[2] += 1

    def add_stage(self, name: str, ms: float) -> None:
        with self._lock:
            self.stages[name] = self.stages.get(name, 0.0) + ms

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def summary(self) -> dict:
        with self._lock:
            usage = {m: list(v) for m, v in self.usage.items()}
            stages = dict(self.stages)
        usd, unpriced = cost_of(usage)
        leaf = {k: v for k, v in stages.items() if k in LEAF}
        busy = sum(leaf.values()) or 1.0
        share = {k: round(100 * v / busy, 1) for k, v in sorted(leaf.items(), key=lambda kv: -kv[1])}
        return {
            "trace_id": self.trace_id, "wall_ms": self.elapsed_ms(), "first_token_ms": self.first_token_ms,
            "stages_ms": {k: int(v) for k, v in sorted(stages.items(), key=lambda kv: -kv[1])},
            "stage_share_pct": share, "top_stage": next(iter(share), None),
            "tokens": {"prompt": sum(v[0] for v in usage.values()), "completion": sum(v[1] for v in usage.values()),
                       "calls": sum(v[2] for v in usage.values())},
            "usage": usage, "cost_usd": round(usd, 6), "unpriced_models": unpriced,
            "question_chars": self.question_chars, **self.attrs,
        }

    def finish(self, status: str = "ok", **extra) -> dict:
        s = {**self.summary(), "status": status, **extra}
        RECENT.append(s)
        log.info(json.dumps({"event": "request", **s}, separators=(",", ":")))
        return s


def current() -> "Trace | None":
    return _current.get()


@contextmanager
def activate(trace: Trace):
    token = _current.set(trace)
    try:
        yield trace
    finally:
        _current.reset(token)


@contextmanager
def stage(name: str):
    """Time a block and add it to the active trace (no-op without one)."""
    t = current()
    start = time.perf_counter()
    try:
        yield
    finally:
        if t is not None:
            t.add_stage(name, (time.perf_counter() - start) * 1000)


def record_usage(model: str, prompt: int, completion: int) -> None:
    t = current()
    if t is not None:
        t.add_usage(model, prompt, completion)


def traced(gen, trace: Trace):
    """Drive a sync generator with `trace` active on every step. Starlette advances sync generators in a worker
    thread per step and discards context changes between steps, so the trace has to be re-activated each time."""
    while True:
        with activate(trace):
            try:
                item = next(gen)
            except StopIteration:
                return
        yield item


def stats() -> dict:
    rows = list(RECENT)
    if not rows:
        return {"requests": 0}
    walls = sorted(r["wall_ms"] for r in rows)
    pct = lambda p: walls[min(len(walls) - 1, int(round(p / 100 * (len(walls) - 1))))]  # noqa: E731
    priced = [r["cost_usd"] for r in rows if not r["unpriced_models"]]
    share: dict[str, list[float]] = {}
    for r in rows:
        for k, v in r["stage_share_pct"].items():
            share.setdefault(k, []).append(v)
    return {
        "requests": len(rows), "errors": sum(r["status"] != "ok" for r in rows),
        "wall_ms_p50": pct(50), "wall_ms_p95": pct(95),
        "tokens_total": sum(r["tokens"]["prompt"] + r["tokens"]["completion"] for r in rows),
        "cost_usd_avg": round(statistics.mean(priced), 6) if priced else None,
        "cost_usd_total": round(sum(priced), 6) if priced else None,
        "requests_with_unpriced_models": sum(bool(r["unpriced_models"]) for r in rows),
        "stage_share_pct_avg": {k: round(statistics.mean(v), 1) for k, v in sorted(share.items(), key=lambda kv: -statistics.mean(kv[1]))},
    }


def setup_logging() -> None:
    """One JSON object per line on stdout for the request logger (idempotent)."""
    if log.handlers:
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False
