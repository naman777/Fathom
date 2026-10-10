import sys
from pathlib import Path

import json

from pgvector import Vector

from core import config, db, llm
from ingest import safety
from ingest.chunking import split_with_headings
from ingest import context


def read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def ingest_text(title: str, text: str, source: str | None = None, conn=None, s3_key: str | None = None) -> dict:
    pieces = split_with_headings(text)
    chunks = [c for c, _ in pieces]
    flags = safety.scan(text)
    if not chunks:
        return {"title": title, "chunks": 0}
    if config.CHUNK_HEADERS:
        desc = context.describe(title, text)
        chunks = [context.header(title, desc, h) + "\n" + c for c, h in pieces]
    vecs = llm.embed(chunks)
    own = conn is None
    conn = conn or db.connect()
    try:
        doc_id = conn.execute(
            "INSERT INTO documents(title, source, s3_key, flags) VALUES (%s,%s,%s,%s) RETURNING id",
            (title, source, s3_key, json.dumps(flags) if flags else None)).fetchone()[0]
        # One binary COPY instead of a round trip per row: 62 chunks took 18 s as row inserts and 0.7 s this way.
        with conn.cursor() as cur, cur.copy(
                "COPY chunks(document_id, position, content, embedding) FROM STDIN WITH (FORMAT BINARY)") as copy:
            copy.set_types(["int4", "int4", "text", "vector"])
            for i, (c, v) in enumerate(zip(chunks, vecs)):
                copy.write_row((doc_id, i, c, Vector(v)))
        return {"document_id": doc_id, "title": title, "chunks": len(chunks), "flags": flags}
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
