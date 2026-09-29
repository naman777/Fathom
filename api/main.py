import json
import time
from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import loop
from core import config, db, obs, storage
from core.ratelimit import rate_limit_middleware
from generation import prompt
from ingest.pipeline import ingest_text, read_file

obs.setup_logging()
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
        rows = c.execute("""SELECT d.id, d.title, d.source, count(c.id), d.s3_key IS NOT NULL, d.flags
                            FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                            GROUP BY d.id ORDER BY d.id DESC""").fetchall()
    return [{"id": r[0], "title": r[1], "source": r[2], "chunks": r[3], "stored": r[4], "flags": r[5] or {}} for r in rows]


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
    trace = obs.Trace(question_chars=len(req.question), agent=req.agent, rerank=req.rerank)

    def gen():
        conn = db.connect()
        finished = False
        try:
            yield sse("meta", {"trace_id": trace.trace_id})
            sources = []
            for ev in loop.run(conn, req.question, req.history, rerank=req.rerank, use_agent=req.agent):
                if ev["type"] == "sources":
                    sources = ev["chunks"]
                    ev = {"type": "sources", "chunks": [
                        {"n": i, "id": c["id"], "title": c["title"], "position": c["position"],
                         "content": c["content"]} for i, c in enumerate(sources, 1)]}
                yield sse("trace", ev)
            yield sse("retrieval_done", {"ms": trace.elapsed_ms()})
            first, t_answer = True, time.perf_counter()
            for tok in prompt.answer_stream(req.question, sources, req.history):
                if first:
                    trace.first_token_ms = trace.elapsed_ms()
                    yield sse("first_token", {"ms": trace.first_token_ms})
                    first = False
                yield sse("token", tok)
            trace.add_stage("answer", (time.perf_counter() - t_answer) * 1000)
            finished = True
            yield sse("done", {"ms": trace.elapsed_ms(), **trace.finish("ok", n_sources=len(sources))})
        except Exception as e:  # surface errors to the UI instead of a dead stream
            finished = True
            trace.finish("error", error=type(e).__name__)
            yield sse("error", str(e))
        finally:
            if not finished:  # client went away mid-stream
                trace.finish("aborted")
            conn.close()

    return StreamingResponse(obs.traced(gen(), trace), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "X-Trace-Id": trace.trace_id})


@app.get("/api/stats")
def stats():
    """Aggregate of the most recent requests: latency, tokens, cost and where the time went."""
    return {**obs.stats(), "priced_models": sorted(config.MODEL_PRICES), "models": {
        "answer": config.CHAT_MODEL, "rerank": config.RERANK_MODEL, "planner": config.PLANNER_MODEL,
        "embed": config.EMBED_MODEL}}


RESULT_FILES = {"synthetic": "results.json", "real": "results_real_rfc.json"}


@app.get("/api/eval-results")
def eval_results():
    """Saved evaluation summaries (per-question rows are dropped) for the Results page."""
    out = {}
    for key, name in RESULT_FILES.items():
        path = config.ROOT / "eval" / "results" / name
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        out[key] = {stage: {"runs": len(r.get("runs", [])), "summary": r["summary"], "by_type": r.get("by_type", {}),
                            "usage": r.get("usage", {})} for stage, r in raw.items()}
    return out
