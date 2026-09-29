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
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "low")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = 1536


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
