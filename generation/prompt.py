from core import llm

SYSTEM = (
    "You are Fathom, a careful research assistant. Answer ONLY using the numbered sources provided. "
    "Cite every factual claim inline with bracketed source numbers like [1] or [2][3]. "
    "If the sources do not contain the answer, say so plainly instead of guessing. "
    "Be concise and well structured."
)


def format_sources(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{i}] ({c['title']}) {c['content']}" for i, c in enumerate(chunks, 1))


def build_messages(question: str, chunks: list[dict], history: list[dict] | None = None):
    msgs = [{"role": "system", "content": SYSTEM}]
    for m in (history or [])[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": f"Sources:\n{format_sources(chunks)}\n\nQuestion: {question}"})
    return msgs


def answer(question: str, chunks: list[dict], history=None) -> str:
    return llm.chat(build_messages(question, chunks, history), temperature=0.1, max_tokens=1200)


def answer_stream(question: str, chunks: list[dict], history=None):
    yield from llm.chat_stream(build_messages(question, chunks, history))
