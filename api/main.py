import json
import time
from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import loop
from core import config, db, storage
from core.ratelimit import rate_limit_middleware
from generation import prompt
from ingest.pipeline import ingest_text, read_file

app = FastAPI(title="Fathom")
app.middleware("http")(rate_limit_middleware)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


class ChatReq(BaseModel):
    question: str
    history: list[dict] = []
    agent: bool = True
    rerank: bool = True


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/health")
def health():
    with db.connect() as c:
        c.execute("SELECT 1")
    return {"ok": True}


@app.get("/api/documents")
def documents():
    with db.connect() as c:
        rows = c.execute("""SELECT d.id, d.title, d.source, count(c.id), d.s3_key IS NOT NULL
                            FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                            GROUP BY d.id ORDER BY d.id DESC""").fetchall()
    return [{"id": r[0], "title": r[1], "source": r[2], "chunks": r[3], "stored": r[4]} for r in rows]


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int):
    with db.connect() as c:
        row = c.execute("DELETE FROM documents WHERE id=%s RETURNING s3_key", (doc_id,)).fetchone()
    if row and row[0] and storage.enabled():
        try:
            storage.delete(row[0])
        except Exception:  # row is gone; an orphaned object is harmless and can be swept later
            pass
    return {"ok": True}


@app.get("/api/documents/{doc_id}/download")
def download_document(doc_id: int):
    with db.connect() as c:
        row = c.execute("SELECT s3_key, source FROM documents WHERE id=%s", (doc_id,)).fetchone()
    if not row or not row[0] or not storage.enabled():
        raise HTTPException(404, "No stored file for this document")
    return {"url": storage.presigned_url(row[0], row[1] or "document"), "expires_in": config.S3_URL_EXPIRES}


@app.post("/api/documents")
async def upload(file: UploadFile = File(...)):
    name = Path(file.filename or "upload.txt")
    if name.suffix.lower() not in {".txt", ".md", ".pdf"}:
        raise HTTPException(400, "Only .txt, .md and .pdf are supported")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {config.MAX_UPLOAD_MB} MB)")
    tmp = Path("data") / "_upload" / name.name
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(data)
    try:
        text = read_file(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    if not text.strip():
        raise HTTPException(400, "No extractable text in file")
    key = None
    if storage.enabled():
        try:
            key = await run_in_threadpool(storage.put, data, name.name, file.content_type)
        except Exception as e:
            raise HTTPException(502, f"Could not store file in S3: {type(e).__name__}")
    try:
        result = ingest_text(name.stem.replace("_", " "), text, name.name, s3_key=key)
    except Exception:
        if key:
            await run_in_threadpool(storage.delete, key)
        raise
    if key and not result.get("document_id"):  # nothing was indexed, so don't keep the file
        await run_in_threadpool(storage.delete, key)
    return result


@app.post("/api/chat")
def chat(req: ChatReq):
    if not req.question.strip():
        raise HTTPException(400, "Empty question")
    if len(req.question) > config.MAX_QUESTION_CHARS:
        raise HTTPException(413, f"Question too long (max {config.MAX_QUESTION_CHARS} characters)")
    req.history = [{"role": m.get("role"), "content": str(m.get("content", ""))[:2000]}
                   for m in req.history[-6:]]
    def gen():
        t0 = time.time()
        conn = db.connect()
        try:
            sources = []
            for ev in loop.run(conn, req.question, req.history, rerank=req.rerank, use_agent=req.agent):
                if ev["type"] == "sources":
                    sources = ev["chunks"]
                    ev = {"type": "sources", "chunks": [
                        {"n": i, "id": c["id"], "title": c["title"], "position": c["position"],
                         "content": c["content"]} for i, c in enumerate(sources, 1)]}
                yield sse("trace", ev)
            yield sse("retrieval_done", {"ms": int((time.time() - t0) * 1000)})
            first = True
            for tok in prompt.answer_stream(req.question, sources, req.history):
                if first:
                    yield sse("first_token", {"ms": int((time.time() - t0) * 1000)})
                    first = False
                yield sse("token", tok)
            yield sse("done", {"ms": int((time.time() - t0) * 1000)})
        except Exception as e:  # surface errors to the UI instead of a dead stream
            yield sse("error", str(e))
        finally:
            conn.close()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
