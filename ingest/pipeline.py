import sys
from pathlib import Path

from core import db, llm
from ingest.chunking import split_text


def read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def ingest_text(title: str, text: str, source: str | None = None, conn=None) -> dict:
    chunks = split_text(text)
    if not chunks:
        return {"title": title, "chunks": 0}
    vecs = llm.embed(chunks)
    own = conn is None
    conn = conn or db.connect()
    try:
        doc_id = conn.execute(
            "INSERT INTO documents(title, source) VALUES (%s,%s) RETURNING id",
            (title, source)).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks(document_id, position, content, embedding) VALUES (%s,%s,%s,%s)",
                [(doc_id, i, c, v) for i, (c, v) in enumerate(zip(chunks, vecs))])
        return {"document_id": doc_id, "title": title, "chunks": len(chunks)}
    finally:
        if own:
            conn.close()


def ingest_path(path: Path, conn=None) -> dict:
    return ingest_text(path.stem.replace("_", " "), read_file(path), path.name, conn)


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/corpus")
    files = [target] if target.is_file() else sorted(
        p for p in target.rglob("*") if p.suffix.lower() in {".txt", ".md", ".pdf"})
    with db.connect() as c:
        for f in files:
            print(ingest_path(f, c))
