import re


def split_text(text: str, target: int = 900, overlap: int = 150) -> list[str]:
    """Paragraph/sentence-aware chunking with character overlap."""
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units = []
    for p in paras:
        if len(p) <= target:
            units.append(p)
        else:
            units.extend(s for s in re.split(r"(?<=[.!?])\s+", p) if s)
    chunks, cur = [], ""
    for u in units:
        if cur and len(cur) + len(u) + 1 > target:
            chunks.append(cur)
            tail = cur[-overlap:]
            sp = tail.find(" ")
            cur = (tail[sp + 1:] if sp >= 0 else tail) + " " + u
        else:
            cur = f"{cur}\n{u}" if cur else u
    if cur.strip():
        chunks.append(cur)
    return chunks
