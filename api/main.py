import json
import threading
from collections import defaultdict
from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from agent import loop
from api import enterprise as enterprise_api
from api.chat import ChatReq, chat_response, validate_chat
from core import config, db, obs, storage
from core.ratelimit import rate_limit_middleware
from eval import real_corpus
from ingest.pipeline import ingest_text, read_file

obs.setup_logging()
app = FastAPI(title="Fathom")
app.middleware("http")(rate_limit_middleware)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


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


_sample_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)  # one ingest per sample file at a time (per process)


@app.get("/api/sample")
def sample():
    """The built-in sample corpus (the RFC set the real-corpus evaluation runs on) and its labelled questions.
    Files are listed smallest first, which is also the fastest order to index them in."""
    golden = json.loads((config.ROOT / "eval" / "real_golden_set.json").read_text(encoding="utf-8"))
    return {"files": [{"name": p.name, "title": real_corpus.title_of(p), "kb": round(p.stat().st_size / 1024)}
                      for p in sorted(real_corpus.files(), key=lambda p: p.stat().st_size)],
            "questions": [{"question": q["question"], "docs": sorted({e["doc"] for e in q["evidence"]})} for q in golden]}


@app.post("/api/sample/{name}")
def load_sample(name: str):
    """Index one sample file (cleaned exactly as for the evaluation). A file that is already present is skipped."""
    path = next((p for p in real_corpus.files() if p.name == name), None)
    if path is None:
        raise HTTPException(404, "Not a sample document")
    title = real_corpus.title_of(path)
    with _sample_locks[name], db.connect() as c:
        if c.execute("SELECT 1 FROM documents WHERE source=%s", (name,)).fetchone():
            return {"title": title, "skipped": True}
        return ingest_text(title, real_corpus.clean(path.read_text(encoding="utf-8", errors="ignore")), name, c)


@app.post("/api/chat")
def chat(req: ChatReq):
    validate_chat(req)
    trace = obs.Trace(question_chars=len(req.question), agent=req.agent, rerank=req.rerank)
    return chat_response(req, trace, db.connect,
                         lambda conn: loop.run(conn, req.question, req.history, rerank=req.rerank, use_agent=req.agent))


app.include_router(enterprise_api.router)


@app.get("/api/stats")
def stats():
    """Aggregate of the most recent requests: latency, tokens, cost and where the time went."""
    return {**obs.stats(), "priced_models": sorted(config.MODEL_PRICES), "prices": config.MODEL_PRICES, "models": {
        "answer": config.CHAT_MODEL, "rerank": config.RERANK_MODEL, "planner": config.PLANNER_MODEL, **({"hyde": config.HYDE_MODEL} if config.HYDE else {}),
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
    for key in ("injection", "upgrades"):  # optional extras: injection test summary, retrieval-upgrade experiment tables
        path = config.ROOT / "eval" / "results" / f"{key}.json"
        if path.exists():
            out[key] = json.loads(path.read_text(encoding="utf-8"))
    ent = {}  # enterprise search: pipeline stages (per-question rows dropped), leak test, embedding and database comparisons
    for key, name in (("stages", "ent_results_dev"), ("leak", "ent_leak_test"), ("embed", "ent_embed_bakeoff"), ("db", "ent_db_compare")):
        path = config.ROOT / "eval" / "results" / f"{name}.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            ent[key] = {s: {k: v for k, v in r.items() if k != "rows"} for s, r in raw.items()} if key == "stages" else raw
    if ent:
        out["enterprise"] = ent
    return out
