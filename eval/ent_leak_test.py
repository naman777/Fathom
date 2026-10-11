"""Measure whether the role filter leaks.

    python -m eval.ent_leak_test [--collection enterprise] [--answers 20]

For every restricted role and every benchmark question that has gold documents:
  1. search as that role (hybrid, 20 candidates, then neighbour expansion, the widest retrieval the API does);
  2. a *leak* is any returned chunk the role may not read. This is checked on every result of every query, not only
     on gold documents. Target: 0.
  3. questions whose gold documents are all forbidden for the role must retrieve none of them (blocked = 100%);
     questions whose gold documents are all allowed are the control: the filter must not cost recall there, so their
     recall is compared with the admin role's on the same questions.
With --answers N, N forbidden questions per role are also answered end to end and judged: an answer that still states
the gold facts would be a leak through some path other than retrieval (LLM calls; off by default).

No LLM is involved in steps 1-3, so the result is deterministic for a given index.
"""
import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor

from core import config
from enterprise import acl, data, search as ent_search, store
from eval import ent_scorer
from generation import prompt

K = 20


def gold_groups(questions, collection) -> dict[str, list[str]]:
    """doc_id -> groups, read back from the index (so the test sees what is actually stored)."""
    ids = sorted({d for q in questions for d in q["expected_doc_ids"]})
    out = {}
    for i in range(0, len(ids), 200):
        flt = store.models.Filter(must=[store.models.FieldCondition(key="doc_id", match=store.models.MatchAny(any=ids[i:i + 200])),
                                        store.models.FieldCondition(key="pos", match=store.models.MatchValue(value=0))])
        pts, _ = store.client().scroll(collection, scroll_filter=flt, limit=400, with_payload=["doc_id", "groups"])
        out.update({p.payload["doc_id"]: p.payload["groups"] for p in pts})
    return out


def retrieve(q, role, collection):
    hits = ent_search.search(q["question"], role, k=K, candidates=K, rerank=False, collection=collection)
    return ent_search.expand(hits, role, config.NEIGHBOR_EXPAND, collection)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default=config.ENT_COLLECTION)
    ap.add_argument("--answers", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()

    questions = [q for q in data.questions() if q["expected_doc_ids"]]
    groups = gold_groups(questions, a.collection)
    questions = [q for q in questions if all(d in groups for d in q["expected_doc_ids"])]
    print(f"{len(questions)} questions with all gold documents indexed")
    with ThreadPoolExecutor(a.concurrency) as ex:
        admin = dict(zip((q["question_id"] for q in questions), ex.map(lambda q: retrieve(q, "admin", a.collection), questions)))

    out, rng = {}, random.Random(0)
    for role, (label, allowed) in acl.ROLES.items():
        if allowed is None:
            continue
        with ThreadPoolExecutor(a.concurrency) as ex:
            results = list(ex.map(lambda q: retrieve(q, role, a.collection), questions))
        leaked_chunks = returned = blocked_ok = forbidden = control = 0
        rec_role, rec_admin, forbidden_qs = [], [], []
        for q, chunks in zip(questions, results):
            returned += len(chunks)
            leaked_chunks += sum(not acl.can_read(role, acl.groups_for(c["source"], c["title"])) for c in chunks)
            readable = [acl.can_read(role, groups[d]) for d in q["expected_doc_ids"]]
            got = {c["doc_id"] for c in chunks}
            if not any(readable):
                forbidden += 1
                blocked_ok += not (got & set(q["expected_doc_ids"]))
                forbidden_qs.append(q)
            elif all(readable):
                control += 1
                rec_role.append(ent_scorer.retrieval_scores(q, chunks, K)["recall"])
                rec_admin.append(ent_scorer.retrieval_scores(q, admin[q["question_id"]], K)["recall"])
        row = {"label": label, "groups": allowed, "queries": len(questions), "chunks_returned": returned,
               "chunks_leaked": leaked_chunks, "forbidden_questions": forbidden, "forbidden_blocked": blocked_ok,
               "control_questions": control,
               "control_recall_role": round(sum(rec_role) / control, 4) if control else None,
               "control_recall_admin": round(sum(rec_admin) / control, 4) if control else None}
        if a.answers and forbidden_qs:
            picked = rng.sample(forbidden_qs, min(a.answers, len(forbidden_qs)))
            stated = 0
            for q in picked:
                chunks = ent_search.search(q["question"], role, k=5, rerank=True, collection=a.collection)
                j = ent_scorer.judge(q, chunks, prompt.answer(q["question"], chunks))
                stated += j["correct"] and j["completeness"] >= 0.5
            row.update({"answers_checked": len(picked), "answers_stating_forbidden_facts": stated})
        out[role] = row
        print(f"{label:28} leaked {leaked_chunks}/{returned} chunks | forbidden questions blocked {blocked_ok}/{forbidden} | "
              f"control recall@{K} {row['control_recall_role']} (admin {row['control_recall_admin']}, n={control})"
              + (f" | answers stating forbidden facts {row['answers_stating_forbidden_facts']}/{row['answers_checked']}" if "answers_checked" in row else ""))
    total = {"chunks_returned": sum(r["chunks_returned"] for r in out.values()), "chunks_leaked": sum(r["chunks_leaked"] for r in out.values()),
             "forbidden_questions": sum(r["forbidden_questions"] for r in out.values()),
             "forbidden_blocked": sum(r["forbidden_blocked"] for r in out.values())}
    path = config.ROOT / "eval" / "results" / "ent_leak_test.json"
    path.write_text(json.dumps({"collection": a.collection, "k": K, "total": total, "roles": out}, indent=2), encoding="utf-8")
    print(f"TOTAL leaked {total['chunks_leaked']}/{total['chunks_returned']} chunks, blocked {total['forbidden_blocked']}/{total['forbidden_questions']}; wrote {path}")


if __name__ == "__main__":
    main()
