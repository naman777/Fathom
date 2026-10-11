"""Enterprise search API: the same streaming chat, over the EnterpriseRAG-Bench corpus in Qdrant, filtered by role.

There is no login on purpose (this is a demo where a visitor switches roles to see the access rules work), but
authorization is real: the role is resolved once per request by `current_role`, mapped to groups on the server, and
applied as a filter inside every Qdrant query. With real authentication only `current_role` changes: it would read the
role from a verified session or token instead of a header.
"""
import json

from fastapi import APIRouter, Depends, Header, HTTPException

from agent import loop
from api.chat import ChatReq, chat_response, validate_chat
from core import config, obs
from enterprise import acl, search as ent_search, store

router = APIRouter(prefix="/api/enterprise")


def current_role(x_demo_role: str | None = Header(default=None)) -> str:
    """The only place the caller's identity is decided. Unknown or missing roles get the least-privileged role."""
    return x_demo_role if x_demo_role in acl.ROLES else acl.DEFAULT_ROLE


def _index() -> dict:
    try:
        info = store.client().get_collection(config.ENT_COLLECTION)
        return {"ready": True, "chunks": info.points_count, "status": str(info.status)}
    except Exception:
        return {"ready": False, "chunks": 0, "status": "unavailable"}


def _examples() -> list[dict]:
    """Benchmark questions offered in the UI, each with the groups its gold documents belong to (enterprise/examples.json,
    written by eval/ent_examples.py), so a visitor can see the same question succeed for one role and not for another."""
    path = config.ROOT / "enterprise" / "examples.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@router.get("/roles")
def roles():
    """Roles for the switcher, what each may read, and what is indexed."""
    return {"roles": [{"id": r, "label": label, "groups": groups} for r, (label, groups) in acl.ROLES.items()],
            "default": acl.DEFAULT_ROLE, "groups": acl.GROUPS, "index": _index(), "examples": _examples(),
            "models": {"embed": config.ENT_EMBED_MODEL, "rerank": config.RERANK_MODEL, "answer": config.CHAT_MODEL}}


@router.post("/chat")
def chat(req: ChatReq, role: str = Depends(current_role)):
    validate_chat(req)
    if not _index()["ready"]:
        raise HTTPException(503, "The enterprise index is not available")
    trace = obs.Trace(question_chars=len(req.question), agent=req.agent, rerank=req.rerank, corpus="enterprise", role=role)
    return chat_response(
        req, trace, lambda: None,
        lambda _conn: loop.run(None, req.question, req.history, rerank=req.rerank, use_agent=req.agent,
                               searcher=lambda q, k: ent_search.search(q, role, k=k, rerank=req.rerank),
                               expander=lambda chunks: ent_search.expand(chunks, role, config.NEIGHBOR_EXPAND)),
        source_fields=("source", "doc_id"))
