"""Pick the example questions shown on the Enterprise page: one benchmark question per access group.

    python -m eval.ent_examples

Each example is a single-document `basic` question, labelled with the groups of its gold document, so the page can say
which roles should be able to answer it. Writes enterprise/examples.json (committed, so the API does not need the dataset).
"""
import json

from core import config
from enterprise import acl, chunking, data

# Shown in this order: readable by everyone first, then one per restricted group.
WANT = [["all"], ["eng"], ["gtm"], ["people"], ["finance"], ["product"]]


# The benchmark has almost no questions about HR or finance documents (1 of its 722 gold documents), so these two are
# hand-written from Slack threads in those channels. They are for the demo only and are not part of any evaluation.
HAND_WRITTEN = [
    {"question": "Who has to sign off on a salary band exception above 10%, and what does a 25% increase need?",
     "groups": ["people"], "question_id": None, "source": "Slack | #people-ops"},
    {"question": "How should a time-sensitive $2,200 trial purchase be submitted to Finance, and how fast is it triaged?",
     "groups": ["finance"], "question_id": None, "source": "Slack | #finance"},
]


def main():
    qs = [q for q in data.questions() if q["question_type"] == "basic" and len(q["expected_doc_ids"]) == 1 and len(q["question"]) < 170]
    need = {q["expected_doc_ids"][0] for q in qs}
    meta = {d["doc_id"]: d for d in data.iter_documents(columns=["doc_id", "source_type", "title"]) if d["doc_id"] in need}
    out = []
    for groups in WANT:
        for q in qs:
            d = meta.get(q["expected_doc_ids"][0])
            if d and acl.groups_for(d["source_type"], d["title"]) == groups:
                out.append({"question": q["question"], "groups": groups, "question_id": q["question_id"],
                            "source": chunking.header(d["source_type"], d["title"] if d["source_type"] == "slack" else "").strip("[]")})
                break
    have = {tuple(e["groups"]) for e in out}
    out += [e for e in HAND_WRITTEN if tuple(e["groups"]) not in have]
    path =config.ROOT / "enterprise" / "examples.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for e in out:
        print(e["groups"], e["source"], "|", e["question"])
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
