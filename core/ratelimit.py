"""Per-IP sliding-window rate limiter (in-memory) for the paid endpoints.

Configured from .env (all optional):
  RATE_LIMIT_ENABLED=true
  RATE_LIMIT_CHAT_PER_MINUTE=6        # /api/chat calls per IP per minute
  RATE_LIMIT_CHAT_PER_DAY=100         # /api/chat calls per IP per 24h (the real bill cap)
  RATE_LIMIT_UPLOAD_PER_HOUR=10       # document uploads per IP per hour
  RATE_LIMIT_DELETE_PER_HOUR=20       # document deletions per IP per hour
  RATE_LIMIT_SAMPLE_PER_HOUR=30       # sample-corpus files indexed per IP per hour (the corpus has 11)
  RATE_LIMIT_GLOBAL_PER_MINUTE=120    # any /api request per IP per minute
  MAX_QUESTION_CHARS=1000
  MAX_UPLOAD_MB=10
  TRUST_PROXY=false                   # true only behind a reverse proxy you control (reads X-Forwarded-For)

State is per-process: with several workers/instances each keeps its own counters, so divide limits accordingly
or move the store to Redis.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from core import config

# (bucket name, path prefix, method or None, limit attr, window seconds)
RULES = [
    ("global", "/api/", None, "GLOBAL_PER_MINUTE", 60),
    ("chat-min", "/api/chat", "POST", "CHAT_PER_MINUTE", 60),
    ("chat-day", "/api/chat", "POST", "CHAT_PER_DAY", 86400),
    ("upload-hour", "/api/documents", "POST", "UPLOAD_PER_HOUR", 3600),
    ("delete-hour", "/api/documents", "DELETE", "DELETE_PER_HOUR", 3600),
    ("sample-hour", "/api/sample", "POST", "SAMPLE_PER_HOUR", 3600),
]


class Limiter:
    def __init__(self):
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.lock = threading.Lock()
        self.last_sweep = time.time()

    def check(self, ip: str, path: str, method: str) -> tuple[bool, int, str]:
        """Returns (allowed, retry_after_seconds, bucket). Counts the request only if every bucket allows it."""
        now = time.time()
        matched = []
        for name, prefix, m, attr, window in RULES:
            limit = getattr(config, "RL_" + attr)
            if limit > 0 and path.startswith(prefix) and (m is None or m == method):
                matched.append((name, limit, window))
        with self.lock:
            self._sweep(now)
            for name, limit, window in matched:
                q = self.hits[(ip, name)]
                while q and q[0] <= now - window:
                    q.popleft()
                if len(q) >= limit:
                    return False, max(1, int(q[0] + window - now) + 1), name
            for name, _, _ in matched:
                self.hits[(ip, name)].append(now)
        return True, 0, ""

    def _sweep(self, now: float):
        if now - self.last_sweep < 300:
            return
        self.last_sweep = now
        for key in [k for k, q in self.hits.items() if not q or q[-1] < now - 86400]:
            del self.hits[key]


limiter = Limiter()


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    if "*" in config.CORS_ORIGINS:
        return {"Access-Control-Allow-Origin": "*"}
    return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"} if origin in config.CORS_ORIGINS else {}


async def rate_limit_middleware(request: Request, call_next):
    if config.RATE_LIMIT_ENABLED and request.method != "OPTIONS":
        ok, retry, bucket = limiter.check(client_ip(request), request.url.path, request.method)
        if not ok:
            msg = ("Daily request limit reached for your IP. Try again later."
                   if bucket == "chat-day" else "Too many requests. Please slow down.")
            return JSONResponse(
                {"detail": msg, "retry_after": retry, "limit": bucket}, status_code=429,
                headers={"Retry-After": str(retry), **_cors_headers(request)})
    return await call_next(request)
