"""The streaming chat response shared by the document chat (api/main.py) and the enterprise chat (api/enterprise.py)."""
import json
import time

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import config, obs
from generation import prompt


class ChatReq(BaseModel):
    question: str
    history: list[dict] = []
    agent: bool = True
    rerank: bool = True


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def validate_chat(req: ChatReq) -> None:
    if not req.question.strip():
        raise HTTPException(400, "Empty question")
    if len(req.question) > config.MAX_QUESTION_CHARS:
        raise HTTPException(413, f"Question too long (max {config.MAX_QUESTION_CHARS} characters)")
    req.history = [{"role": m.get("role"), "content": str(m.get("content", ""))[:2000]}
                   for m in req.history[-6:]]


def chat_response(req: ChatReq, trace: obs.Trace, open_conn, events, source_fields: tuple = ()):
    """Stream one chat answer as SSE. `events(conn)` yields the retrieval trace events (agent/loop.py); `open_conn`
    returns something with close(), or None."""
    def gen():
        conn = open_conn()
        finished = False
        try:
            yield sse("meta", {"trace_id": trace.trace_id})
            sources = []
            for ev in events(conn):
                if ev["type"] == "sources":
                    sources = ev["chunks"]
                    ev = {"type": "sources", "chunks": [
                        {"n": i, "id": c["id"], "title": c["title"], "position": c["position"],
                         "content": c["content"], **{f: c[f] for f in source_fields}} for i, c in enumerate(sources, 1)]}
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
            if conn is not None:
                conn.close()

    return StreamingResponse(obs.traced(gen(), trace), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "X-Trace-Id": trace.trace_id})
