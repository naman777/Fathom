import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            v = m.group(2)
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(m.group(1), v)


_load_env()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DB_URL = os.environ.get("DB_URL", "")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-6-luna")
# Cheaper/faster models for the small structured calls (default to CHAT_MODEL)
RERANK_MODEL = os.environ.get("RERANK_MODEL", "gpt-4.1-mini")
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "gpt-4.1-mini")
# Reranker backend: "local" (ONNX cross-encoder, fast, no API cost) or "llm"
RERANKER = os.environ.get("RERANKER", "llm").lower()
LOCAL_RERANK_MODEL = os.environ.get("LOCAL_RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-12-v2")
LOCAL_RERANK_CANDIDATES = int(os.environ.get("LOCAL_RERANK_CANDIDATES", "20"))
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "low")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = 1536
# Chunking (characters). Changing these only affects documents ingested afterwards.
CHUNK_TARGET = int(os.environ.get("CHUNK_TARGET", "900"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "150"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# --- abuse / cost protection (0 disables an individual limit) ---
RATE_LIMIT_ENABLED = _bool("RATE_LIMIT_ENABLED", True)
RL_CHAT_PER_MINUTE = _int("RATE_LIMIT_CHAT_PER_MINUTE", 6)
RL_CHAT_PER_DAY = _int("RATE_LIMIT_CHAT_PER_DAY", 100)
RL_UPLOAD_PER_HOUR = _int("RATE_LIMIT_UPLOAD_PER_HOUR", 10)
RL_GLOBAL_PER_MINUTE = _int("RATE_LIMIT_GLOBAL_PER_MINUTE", 120)
MAX_QUESTION_CHARS = _int("MAX_QUESTION_CHARS", 1000)
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 10)
TRUST_PROXY = _bool("TRUST_PROXY", False)
RL_DELETE_PER_HOUR = _int("RATE_LIMIT_DELETE_PER_HOUR", 20)
# Comma-separated allowed browser origins, or "*" (dev only). E.g. https://fathom.example.com
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]

# --- original-file storage on S3 (disabled when AWS_S3_BUCKET is empty) ---
# Credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (read by boto3 from the environment).
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "").strip()
AWS_REGION = os.environ.get("AWS_REGION", "").strip() or None
S3_PREFIX = os.environ.get("S3_PREFIX", "documents").strip("/")
S3_URL_EXPIRES = _int("S3_URL_EXPIRES_SECONDS", 300)
