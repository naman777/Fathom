"""Real-corpus helper: 11 IETF RFCs (plain text from rfc-editor.org, in data/real_corpus/).

  python -m eval.real_corpus --clean DIR   write cleaned text to DIR (what the golden-set quotes are taken from)
  python -m eval.real_corpus --ingest      clean + embed + insert (skips RFCs already present)
  python -m eval.real_corpus --remove      delete the RFC documents this script ingested (source 'RFC_*.txt')

RFC text is hard-wrapped at 72 columns with a page header/footer every ~55 lines, so it is unwrapped and
de-paged before chunking; otherwise passages are split mid-sentence by page furniture.
"""
import re
import sys

from core import config, db
from ingest.pipeline import ingest_text

DIR = config.ROOT / "data" / "real_corpus"
PAGE_FOOTER = re.compile(r"^.*\[Page \d+\]\s*$")
PAGE_HEADER = re.compile(r"^RFC \d+ .{5,}\d{4}\s*$")


def clean(raw: str) -> str:
    lines = [ln.rstrip() for ln in raw.replace("\f", "\n").splitlines()]
    lines = [ln for ln in lines if not PAGE_FOOTER.match(ln) and not PAGE_HEADER.match(ln)]
    paras, cur = [], []
    for ln in lines:
        # blank line or an indented-less heading/list boundary ends the paragraph; body text is indented 3 spaces
        if not ln.strip():
            if cur:
                paras.append(" ".join(cur))
                cur = []
        else:
            cur.append(ln.strip())
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(re.sub(r"\s{2,}", " ", p) for p in paras)


def title_of(path) -> str:
    return path.stem.replace("_", " ")


def files():
    return sorted(DIR.glob("RFC_*.txt"))


def ingest():
    with db.connect() as c:
        have = {r[0] for r in c.execute("SELECT source FROM documents")}
        for p in files():
            if p.name in have:
                print("skip", p.name)
                continue
            print(ingest_text(title_of(p), clean(p.read_text(encoding="utf-8", errors="ignore")), p.name, c), flush=True)


def remove():
    with db.connect() as c:
        n = c.execute("DELETE FROM documents WHERE source LIKE 'RFC\\_%.txt'").rowcount
    print("removed", n, "documents")


if __name__ == "__main__":
    if "--ingest" in sys.argv:
        ingest()
    elif "--remove" in sys.argv:
        remove()
    elif "--clean" in sys.argv:
        out = sys.argv[sys.argv.index("--clean") + 1]
        import pathlib
        pathlib.Path(out).mkdir(parents=True, exist_ok=True)
        for p in files():
            (pathlib.Path(out) / (p.stem + ".txt")).write_text(clean(p.read_text(encoding="utf-8", errors="ignore")), encoding="utf-8")
        print("cleaned", len(files()), "files to", out)
    else:
        print(__doc__)
