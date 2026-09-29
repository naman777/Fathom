import re

from core import config

_NUMBERED = re.compile(r"^(\d+(\.\d+)*\.?|[A-Z]\.\d*|Appendix [A-Z]\.?)\s+\S")


def is_heading(p: str) -> bool:
    """Heuristic: markdown heading, or a short unpunctuated numbered/appendix/all-caps line ("4.1.1. Issuer Claim")."""
    if p.startswith("#"):
        return True
    if "\n" in p or len(p) > 90 or p.endswith((".", ",", ";", ":", "?")) or " . . " in p:  # sentences and ToC lines
        return False
    if _NUMBERED.match(p):
        return len(p.split()) <= 14
    return p.isupper() and len(p) > 3


def split_with_headings(text: str, target: int | None = None, overlap: int | None = None) -> list[tuple[str, str]]:
    """Paragraph/sentence-aware chunking with character overlap (defaults from config.CHUNK_*).
    Returns (chunk, heading) pairs, where heading is the nearest heading at or before the chunk's first new paragraph."""
    target = target or config.CHUNK_TARGET
    overlap = config.CHUNK_OVERLAP if overlap is None else overlap
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units, heads, head = [], [], ""
    for p in paras:
        if is_heading(p):
            head = p.lstrip("# ").strip()[:100]
        parts = [p] if len(p) <= target else [s for s in re.split(r"(?<=[.!?])\s+", p) if s]
        units.extend(parts)
        heads.extend([head] * len(parts))
    chunks, cur, cur_head = [], "", ""
    for u, h in zip(units, heads):
        if cur and len(cur) + len(u) + 1 > target:
            chunks.append((cur, cur_head))
            tail = cur[-overlap:]
            sp = tail.find(" ")
            cur, cur_head = (tail[sp + 1:] if sp >= 0 else tail) + " " + u, h
        else:
            if not cur:
                cur_head = h
            cur = f"{cur}\n{u}" if cur else u
    if cur.strip():
        chunks.append((cur, cur_head))
    return chunks


def split_text(text: str, target: int | None = None, overlap: int | None = None) -> list[str]:
    return [c for c, _ in split_with_headings(text, target, overlap)]
