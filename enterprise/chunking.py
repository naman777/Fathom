"""Chunking for the enterprise corpus.

The corpus is messy in ways the upload-side chunker never sees (measured by eval/ent_profile.py): a Slack "document" is a
whole conversation of about 3,000 characters, 95% of Gmail documents are a Python list literal of raw emails with
escaped newlines, and tickets are a series of `field:` sections. So:

1. normalise  - unpack Gmail threads into separate emails, turn literal "\\n" back into newlines.
2. split      - into natural units: one Slack message, one email paragraph, one transcript turn, one ticket section.
3. pack       - units greedily up to `target` characters, never cutting inside a unit unless the unit itself is too long.
                The last unit is repeated at the start of the next chunk when it fits in `overlap`.
4. header     - every chunk starts with "[Source | title]" so a chunk from the middle of a thread still says where it
                came from. This is built from metadata, so it costs no LLM call (the upload side's CHUNK_HEADERS does).

Target is in characters; 1,200 is about 300 tokens, inside the 512-token window of the embedding models.
"""
import ast
import re

LABELS = {"slack": "Slack", "gmail": "Gmail", "linear": "Linear", "google_drive": "Google Drive", "hubspot": "HubSpot",
          "fireflies": "Meeting transcript", "github": "GitHub", "jira": "Jira", "confluence": "Confluence"}
_CHANNEL = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
_BLANK = re.compile(r"\n\s*\n")
_SENT = re.compile(r"(?<=[.!?])\s+")


def normalize(source: str, content: str) -> str:
    text = content or ""
    if source == "gmail" and text.lstrip().startswith("["):
        try:
            parts = ast.literal_eval(text.strip())
            if isinstance(parts, (list, tuple)):
                text = "\n\n".join(str(p).strip() for p in parts if str(p).strip())
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            pass  # not a clean list literal: fall through to the escaped-newline repair below
    if "\\n" in text and text.count("\n") * 4 < text.count("\\n"):
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    return text.replace("\r\n", "\n").strip()


def header(source: str, title: str) -> str:
    title = " ".join((title or "").split())[:120]
    if source == "slack" and _CHANNEL.match(title):
        title = "#" + title
    return f"[{LABELS.get(source, source)} | {title}]" if title else f"[{LABELS.get(source, source)}]"


def _split_long(unit: str, target: int) -> list[str]:
    """A unit longer than the target: fall back to lines, then sentences, then a hard cut."""
    if len(unit) <= target:
        return [unit]
    out = []
    for sep in ("\n", _SENT):
        parts = [p for p in (unit.split(sep) if isinstance(sep, str) else sep.split(unit)) if p.strip()]
        if len(parts) > 1:
            for p in parts:
                out.extend(_split_long(p.strip(), target))
            return out
    return [unit[i:i + target] for i in range(0, len(unit), target)]


def units(text: str, target: int) -> list[str]:
    parts = _BLANK.split(text) if _BLANK.search(text) else text.split("\n")
    out = []
    for p in parts:
        if p.strip():
            out.extend(_split_long(p.strip(), target))
    return out


def chunk(source: str, title: str, content: str, target: int = 1200, overlap: int = 200) -> list[str]:
    """Return the chunk texts for one document, each prefixed with its header."""
    head = header(source, title)
    us = units(normalize(source, content), target)
    if not us:
        return [head] if title else []
    chunks, cur, size = [], [], 0
    for u in us:
        if cur and size + len(u) + 2 > target:
            chunks.append(cur)
            cur = [cur[-1]] if len(cur) > 1 and len(cur[-1]) <= overlap else []  # carry the last unit as overlap
            size = sum(len(x) + 2 for x in cur)
        cur.append(u)
        size += len(u) + 2
    chunks.append(cur)
    return [head + "\n" + "\n\n".join(c) for c in chunks]
