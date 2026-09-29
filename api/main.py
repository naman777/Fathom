import json
import time
from pathlib import Path

import hmac

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import loop
from core import config, db
from core.ratelimit import rate_limit_middleware
from generation import prompt
from ingest.pipeline import ingest_text, read_file

app = FastAPI(title="Fathom")
app.middleware("http")(rate_limit_middleware)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def require_admin(x_admin_token: str = Header(default="")):
    """Protects mutating document endpoints when ADMIN_TOKEN is configured."""
    if config.ADMIN_TOKEN and not hmac.compare_digest(x_admin_token, config.ADMIN_TOKEN):
        raise HTTPException(401, "Admin token required to modify documents")


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
        rows = c.execute("""SELECT d.id, d.title, d.source, count(c.id)
                            FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                            GROUP BY d.id ORDER BY d.id DESC""").fetchall()
    return [{"id": r[0], "title": r[1], "source": r[2], "chunks": r[3]} for r in rows]


@app.delete("/api/documents/{doc_id}", dependencies=[Depends(require_admin)])
def delete_document(doc_id: int):
    with db.connect() as c:
        c.execute("DELETE FROM documents WHERE id=%s", (doc_id,))
    return {"ok": True}


@app.post("/api/documents", dependencies=[Depends(require_admin)])
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
    return ingest_text(name.stem.replace("_", " "), text, name.name)


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
